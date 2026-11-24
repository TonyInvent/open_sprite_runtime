#include "icm_packet.hpp"
#include "policy_imu_client.hpp"
#include <algorithm>
#include <iostream>
#include <vector>

namespace {
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

// UNIX datagrams only. No sensor, CAN, motor, or input-device access.
class Peer {
    int fd_ = -1;
    std::string directory_, path_;
    std::atomic<bool> stop_{false};
    std::thread thread_;
public:
    std::atomic<int> fault{0}; // 1: freeze; 2: silence; 3: malformed; 4: regression
    std::atomic<unsigned> requests{0};
    std::atomic<bool> failed{false};
    Peer() {
        char pattern[] = "/tmp/sprite_imu_client_test_XXXXXX";
        auto* dir = ::mkdtemp(pattern);
        require(dir != nullptr, "temporary directory");
        directory_ = dir; path_ = directory_ + "/imu.sock";
        sockaddr_un addr{}; addr.sun_family = AF_UNIX;
        std::strcpy(addr.sun_path, path_.c_str());
        fd_ = ::socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        require(fd_ >= 0, "socket");
        require(::bind(fd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0, "bind");
        thread_ = std::thread([this] {
            sprite_imu::Packet packet{};
            std::uint64_t sequence = 0, next = 0;
            while (!stop_) {
                pollfd p{fd_, POLLIN, 0};
                if (::poll(&p, 1, 10) != 1) continue;
                char request[9]{}; sockaddr_un peer{}; socklen_t size = sizeof(peer);
                auto n = ::recvfrom(fd_, request, sizeof(request), MSG_DONTWAIT,
                                    reinterpret_cast<sockaddr*>(&peer), &size);
                if (n != 8 || std::memcmp(request, "GETIMU01", 8)) { failed = true; continue; }
                ++requests;
                const int f = fault.load();
                if (f == 2) continue;
                auto now = sprite_policy::monotonic_ns();
                if (!sequence || (f != 1 && now >= next)) {
                    next = now + 1250000;
                    packet = sprite_imu::encode_icm({-8192, 12, -34, 56, -78, 90},
                        {.001, -.002, .003}, {1, 0, 0, 0}, ++sequence, now, now);
                }
                auto response = packet;
                if (f == 3) response[0] = 0;
                if (f == 4) sprite_imu::put64(response, 8, 1);
                ::sendto(fd_, response.data(), response.size(), MSG_DONTWAIT,
                         reinterpret_cast<sockaddr*>(&peer), size);
            }
        });
    }
    ~Peer() {
        stop_ = true; thread_.join(); ::close(fd_);
        ::unlink(path_.c_str()); ::rmdir(directory_.c_str());
    }
    const std::string& path() const { return path_; }
};

void check_fault(int mode, const std::string& expected) {
    Peer peer;
    sprite_policy::NativeImuClient client(peer.path(), false, true);
    sprite_policy::ImuSnapshot sample;
    const auto start = std::chrono::steady_clock::now();
    while (!client.snapshot(sample) || sample.sequence < 3) {
        require(std::chrono::steady_clock::now() - start < std::chrono::seconds(1), "startup timeout");
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    peer.fault = mode;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (std::chrono::steady_clock::now() < deadline) {
        try { client.snapshot(sample); }
        catch (const std::runtime_error& e) {
            require(std::string(e.what()).find(expected) != std::string::npos, "wrong rejection reason");
            require(!peer.failed, "unexpected request");
            return;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    throw std::runtime_error("fault was not rejected");
}
}

int main() {
    try {
        static_assert(sprite_policy::imu_snapshot_period(true).count() == 1250);
        static_assert(sprite_policy::imu_snapshot_period(false).count() == 5000);
        Peer peer;
        {
            sprite_policy::NativeImuClient client(peer.path(), false, true);
            sprite_policy::ImuSnapshot sample;
            std::uint64_t previous = 0;
            unsigned received = 0;
            std::vector<double> ages;
            const auto start = std::chrono::steady_clock::now();
            for (unsigned i = 0; i < 100; ++i) {
                std::this_thread::sleep_until(start + std::chrono::milliseconds(20 * (i + 1)));
                if (!client.snapshot(sample)) continue;
                require(sample.sequence >= previous, "sequence regressed");
                previous = sample.sequence; ++received;
                const auto expected = sprite_imu::encode_icm({-8192, 12, -34, 56, -78, 90},
                    {.001, -.002, .003}, {1, 0, 0, 0}, sample.sequence, sample.start, sample.end);
                auto decoded = sprite_policy::validate_imu_packet(expected.data(), expected.size(),
                    sprite_policy::monotonic_ns(), 0, false, true);
                require(sample.values == decoded.values, "snapshot changed estimator values");
                ages.push_back((sprite_policy::monotonic_ns() - sample.start) / 1e6);
            }
            const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            require(received == 100 && !peer.failed, "incomplete snapshots");
            // Report scheduling performance, do not turn host load into a relaxed safety gate.
            std::sort(ages.begin(), ages.end());
            std::cout << "icm_v3_shared_client requests_hz=" << peer.requests / elapsed
                      << " policy_snapshots=" << received << " age_median_ms=" << ages[50]
                      << " age_max_ms=" << ages.back() << "\n";
        }
        check_fault(1, "stale"); check_fault(2, "timeout");
        check_fault(3, "size/version"); check_fault(4, "regression");
        std::cout << "PASS: both icm-v3 backends, unchanged values, stale/timeout/malformed/regression rejection; NO HARDWARE\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
