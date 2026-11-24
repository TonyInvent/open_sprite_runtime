#pragma once
#include "core.hpp"
#include <linux/can.h>

namespace openimu {
constexpr uint64_t max_age_ns = 30000000;

struct Sample {
  uint16_t tick;
  inv_imu_sensor_data_t raw{};
};

inline Sample decode(const canfd_frame& frame, size_t bytes) {
  if (bytes != CANFD_MTU || frame.can_id != 1 || frame.len != 16 ||
      !(frame.flags & CANFD_BRS))
    throw std::runtime_error("unexpected OpenIMU CAN FD frame");
  auto word = [&](int i) { return uint16_t((frame.data[i] << 8) | frame.data[i+1]); };
  Sample s{word(0)};
  for (int axis = 0; axis < 3; ++axis) {
    s.raw.accel_data[axis] = int16_t(word(2+2*axis));
    s.raw.gyro_data[axis] = int16_t(word(8+2*axis));
  }
  s.raw.temp_data = int16_t(word(14));
  return s;
}

// The filter integrates in sensor time. IPC freshness uses host time. Track
// excess transport delay relative to the earliest arrivals, allowing 2% clock
// drift between the independent oscillators.
class SampleClock {
  uint16_t last_tick_ = 0;
  uint64_t last_rx_ = 0, estimated_ = 0;
public:
  uint64_t sensor_ns = 0;
  uint64_t update(uint16_t tick, uint64_t rx, uint64_t now) {
    if (!rx || now < rx || now-rx >= max_age_ns)
      throw std::runtime_error("stale OpenIMU kernel RX timestamp");
    if (!last_rx_) {
      estimated_ = sensor_ns = rx;
    } else {
      uint64_t delta = uint64_t(uint16_t(tick-last_tick_))*1000;
      if (rx < last_rx_ || rx-last_rx_ >= max_age_ns || delta == 0 || delta >= max_age_ns)
        throw std::runtime_error("OpenIMU timestamp gap or repeat");
      sensor_ns += delta;
      estimated_ = std::min(rx, estimated_ + delta + delta/50);
      if (now-estimated_ >= max_age_ns)
        throw std::runtime_error("OpenIMU stream exceeded freshness limit");
    }
    last_rx_ = rx;
    last_tick_ = tick;
    return estimated_;
  }
};
}
