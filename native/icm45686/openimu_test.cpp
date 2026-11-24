#include "openimu.hpp"

void require(bool condition) {
  if (!condition) throw std::runtime_error("OpenIMU regression");
}
template<class F> void rejects(F f) {
  try { f(); } catch (const std::runtime_error&) { return; }
  throw std::runtime_error("invalid OpenIMU input accepted");
}

int main() {
  canfd_frame frame{};
  frame.can_id = 1;
  frame.len = 16;
  frame.flags = CANFD_BRS;
  uint8_t data[] = {0xff,0xf0, 0xe0,0, 0,1, 0xff,0xff, 0x7f,0xff, 0x80,0, 1,2, 0xff,0x80};
  std::memcpy(frame.data, data, sizeof(data));
  auto s = openimu::decode(frame, CANFD_MTU);
  require(s.tick == 65520 && s.raw.accel_data[0] == -8192 && s.raw.accel_data[1] == 1 &&
          s.raw.accel_data[2] == -1 && s.raw.gyro_data[0] == 32767 && s.raw.gyro_data[1] == -32768 &&
          s.raw.gyro_data[2] == 258 && s.raw.temp_data == -128);
  require(icm::body(icm::accel(s.raw))[2] == sprite_imu::gravity);
  rejects([&] { openimu::decode(frame, CAN_MTU); });
  for (auto id : {2U, 1U|CAN_EFF_FLAG, 1U|CAN_RTR_FLAG, 1U|CAN_ERR_FLAG}) {
    auto bad = frame; bad.can_id = id;
    rejects([&] { openimu::decode(bad, CANFD_MTU); });
  }
  auto bad = frame; bad.len = 12;
  rejects([&] { openimu::decode(bad, CANFD_MTU); });
  bad = frame; bad.flags = 0;
  rejects([&] { openimu::decode(bad, CANFD_MTU); });

  uint64_t rx = 1000000000, start = rx;
  openimu::SampleClock clock;
  uint16_t tick = s.tick;
  for (unsigned i = 0; i < 12010; ++i) {
    require(clock.update(tick, rx, rx+20000) == rx);
    require(clock.sensor_ns == rx);
    tick += 1250; rx += 1250000;
  }
  require(clock.sensor_ns-start > 15000000000ULL);
  rejects([&] { clock.update(uint16_t(tick-1250), rx, rx); });
  rejects([&] { clock.update(tick, rx, rx+30000000); });
  rejects([&] { clock.update(tick, rx+65536000, rx+65536000); });
  rejects([&] { clock.update(uint16_t(tick+30000), rx, rx); });
  // Two samples arrived in a USB burst following a brief transport delay.
  auto estimate = clock.update(tick, rx+4000000, rx+4010000);
  require(estimate < rx+4000000 && estimate >= rx);
  require(clock.update(uint16_t(tick+1250), rx+4000000, rx+4020000) > estimate);
}
