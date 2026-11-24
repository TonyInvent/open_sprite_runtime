// Adapted from TonyInvent/MacMimic bc7be0a5868f85bbe1f3dc9a4a7c9de3a99788d9 (AGPL-3.0).
#include "openimu.hpp"
#include "ipc.hpp"
#include <linux/can/raw.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <csignal>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <vector>

namespace {
volatile std::sig_atomic_t stopping = 0;
void stop(int) { stopping = 1; }
uint64_t nanos(timespec t) { return uint64_t(t.tv_sec)*1000000000 + t.tv_nsec; }
uint64_t clock_ns(clockid_t clock) {
  timespec t{};
  if (clock_gettime(clock, &t)) throw std::runtime_error("clock_gettime failed");
  return nanos(t);
}
struct Receiver {
  int fd = socket(PF_CAN, SOCK_RAW|SOCK_CLOEXEC, CAN_RAW);
  ~Receiver() { if (fd >= 0) close(fd); }
  void bind_interface(const char* name) {
    if (fd < 0) throw std::runtime_error("OpenIMU socket creation failed");
    ifreq device{};
    if (!*name || std::strlen(name) >= IFNAMSIZ) throw std::runtime_error("invalid CAN interface");
    std::strcpy(device.ifr_name, name);
    if (ioctl(fd, SIOCGIFMTU, &device) || device.ifr_mtu != CANFD_MTU ||
        ioctl(fd, SIOCGIFFLAGS, &device) || !(device.ifr_flags & IFF_UP))
      throw std::runtime_error("OpenIMU interface must be UP in CAN FD mode");
    int yes = 1;
    can_filter filter{1, CAN_SFF_MASK|CAN_EFF_FLAG|CAN_RTR_FLAG};
    if (setsockopt(fd, SOL_CAN_RAW, CAN_RAW_FD_FRAMES, &yes, sizeof(yes)) ||
        setsockopt(fd, SOL_CAN_RAW, CAN_RAW_FILTER, &filter, sizeof(filter)) ||
        setsockopt(fd, SOL_SOCKET, SO_TIMESTAMPNS, &yes, sizeof(yes)) ||
        setsockopt(fd, SOL_SOCKET, SO_RXQ_OVFL, &yes, sizeof(yes)))
      throw std::runtime_error("OpenIMU socket options failed");
    sockaddr_can address{};
    address.can_family = AF_CAN;
    address.can_ifindex = if_nametoindex(name);
    if (!address.can_ifindex || bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)))
      throw std::runtime_error("OpenIMU SocketCAN bind failed");
  }
};

struct Record {
  uint64_t rx, read, estimated;
  openimu::Sample sample;
};
}

int capture_openimu(int argc, char** argv) {
  if (argc != 5) throw std::runtime_error("capture-canfd IFACE SECONDS CSV");
  const double seconds = std::stod(argv[3]);
  if (!std::isfinite(seconds) || seconds < 20 || seconds > 600)
    throw std::runtime_error("duration must be 20..600s including bias");
  if (!access(argv[4], F_OK)) throw std::runtime_error("capture file already exists");
  Receiver socket;
  socket.bind_interface(argv[2]);
  IcmServer server(std::getenv("ICM_IPC_SOCKET"));
  std::ofstream csv(argv[4]);
  if (!csv) throw std::runtime_error("cannot open OpenIMU capture file");
  csv << "kernel_rx_ns,read_ns,estimated_sample_ns,sensor_tick_us,raw_ax,raw_ay,raw_az,raw_gx,raw_gy,raw_gz,raw_temp\n";
  sprite_imu::StaticBias bias;
  sprite_imu::SixAxis filter;
  openimu::SampleClock timeline;
  std::vector<Record> rows;
  rows.reserve(size_t(seconds*820));
  bool ready = false;
  std::cout << "OPENIMU_RX_ONLY: 800Hz, X_DOWN_Z_BACK; keep still for 15s" << std::endl;
  // SCM_TIMESTAMPNS is CLOCK_REALTIME. Use a fixed conversion so batched
  // datagrams retain their arrival spacing. Detect wall-clock steps.
  const auto mono_anchor = clock_ns(CLOCK_MONOTONIC);
  const auto real_anchor = clock_ns(CLOCK_REALTIME);
  const auto offset = real_anchor-mono_anchor;
  std::signal(SIGINT, stop);
  std::signal(SIGTERM, stop);
  std::string error;
  try {
    while (!stopping && clock_ns(CLOCK_MONOTONIC)-mono_anchor < uint64_t(seconds*1e9)) {
      pollfd p{socket.fd, POLLIN, 0};
      const int result = poll(&p, 1, rows.empty() ? 1000 : 30);
      if (result < 0 && errno == EINTR) continue;
      if (result != 1 || p.revents != POLLIN) throw std::runtime_error("OpenIMU stream timeout/error");
      canfd_frame frame{};
      iovec iov{&frame, sizeof(frame)};
      alignas(cmsghdr) char control[CMSG_SPACE(sizeof(timespec))+CMSG_SPACE(sizeof(uint32_t))]{};
      msghdr msg{};
      msg.msg_iov = &iov;
      msg.msg_iovlen = 1;
      msg.msg_control = control;
      msg.msg_controllen = sizeof(control);
      auto bytes = recvmsg(socket.fd, &msg, MSG_DONTWAIT);
      if (bytes < 0 || msg.msg_flags & (MSG_TRUNC|MSG_CTRUNC))
        throw std::runtime_error("OpenIMU incomplete recvmsg");
      auto sample = openimu::decode(frame, size_t(bytes));
      uint64_t arrival = 0;
      for (auto* c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
        if (c->cmsg_level != SOL_SOCKET) continue;
        if (c->cmsg_type == SO_RXQ_OVFL) throw std::runtime_error("OpenIMU socket dropped frames");
        if (c->cmsg_type == SCM_TIMESTAMPNS && c->cmsg_len == CMSG_LEN(sizeof(timespec))) {
          timespec stamp{};
          std::memcpy(&stamp, CMSG_DATA(c), sizeof(stamp));
          arrival = nanos(stamp);
        }
      }
      const auto real = clock_ns(CLOCK_REALTIME);
      const auto now = clock_ns(CLOCK_MONOTONIC);
      if (arrival <= offset || real < offset || std::llabs(int64_t(real-offset)-int64_t(now)) > 1000000)
        throw std::runtime_error("OpenIMU host RX clock discontinuity");
      const auto rx = arrival-offset;
      const auto estimated = timeline.update(sample.tick, rx, now);
      const auto a = icm::body(icm::accel(sample.raw)), w = icm::body(icm::gyro(sample.raw));
      rows.push_back({rx, now, estimated, sample});
      if (!ready) {
        bias.add(a, w, timeline.sensor_ns);
        if (!bias.ready() || now-mono_anchor < 15000000000ULL) continue;
        filter.initialize(bias.acceleration(), bias.bias(), timeline.sensor_ns);
        ready = true;
        std::cout << "BIAS_READY: movement may begin" << std::endl;
      } else {
        filter.update(a, w, timeline.sensor_ns);
      }
      std::array<int16_t, 6> counts{};
      for (int i = 0; i < 3; ++i) {
        counts[i] = sample.raw.accel_data[i];
        counts[3+i] = sample.raw.gyro_data[i];
      }
      server.publish(sprite_imu::encode_icm(counts, icm::body(bias.bias()), filter.quaternion(),
                                            rows.size(), estimated, now));
    }
    if (!ready) throw std::runtime_error("OpenIMU stationary bias incomplete");
  } catch (const std::exception& e) { error = e.what(); }
  for (const auto& r : rows) {
    csv << r.rx << ',' << r.read << ',' << r.estimated << ',' << r.sample.tick;
    for (auto v : r.sample.raw.accel_data) csv << ',' << v;
    for (auto v : r.sample.raw.gyro_data) csv << ',' << v;
    csv << ',' << r.sample.raw.temp_data << '\n';
  }
  csv.close();
  if (!csv) throw std::runtime_error("OpenIMU capture write failed");
  if (!error.empty()) throw std::runtime_error(error);
  return stopping ? 1 : 0;
}
