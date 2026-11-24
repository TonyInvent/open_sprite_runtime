# OpenIMU timestamp and standing-oscillation audit

## Scope

The operator reported mild whole-body oscillation while standing, reduced when
walking, with both IMU backends and subjectively more with OpenIMU. This audit
uses completed recordings only. No hardware command, gain change, sensor
configuration, automatic backend switch or new powered test was performed.
The two backends are evaluated as separate, mutually exclusive policy inputs.

Evidence copied to the Windows workspace:

- OpenIMU session `xbox_openimu_e4tafunt`, actor stamp `20261124_145953`.
- SPI capture `xbox_imu_turn120_jxWQZajo`, actor stamp `20261124_145600`.
- Offline analysis: `work/openimu_review_20261124/standing_audit.json` and
  `alignment_audit.json`, with reproducible `audit_standing.py`,
  `audit_alignment.py`, `replay_clock.cpp`, and generated `clock_replay.csv`.
- Published firmware inspected at TonyInvent/OpenIMU commit
  `e70e680753cc4a370d5c148cb0d2bb2bd7f4d75d`. Source inspection does not establish
  the exact flashed firmware version; the transmit-only protocol has no version
  or configuration readback in this runtime.

## Timestamp path

The inspected firmware enables FIFO timestamps with a 1 us resolution and
absolute, not delta, counter mode. It decodes the sensor's FIFO byte order and
packs the counter into the first two CAN payload bytes, high byte first.
The host decoder reads the same unsigned 16-bit big-endian value. It computes:

```text
delta_us = uint16_t(current_tick - previous_tick)
sensor_time_ns += delta_us * 1000
estimator.update(accel_body, gyro_body, sensor_time_ns)
```

Thus wrap at 65,536 us is handled by modulo subtraction. The estimator does
not integrate using CAN delivery jitter or policy tick duration. Kernel receive
time and the host-aligned sample estimate are used separately for freshness.

In the completed OpenIMU capture, all 117,667 adjacent tick differences were
1,250 us. No duplicate tick or gap was observed. An offline replay through the
unchanged production `SampleClock` reproduced every recorded host-aligned sample
timestamp exactly. Gravity increments at counter wraps had median 0.002998 deg
and p99 0.041665 deg; non-wrap increments were 0.002913 and 0.040551 deg.
There is no observed wrap-linked attitude discontinuity in this recording.

The full production estimator was replayed from recorded raw samples, including
startup bias. Each of the 6,001 OpenIMU actor input snapshots matched a replayed
gyro/gravity pair with maximum Euclidean error `1.10e-15`. The SPI actor inputs
matched their own sensor recording with maximum error `1.07e-15`. No consumed
sample sequence regression or repeat was found. The observation float fields
also matched the expected body rotation and projected-gravity conversion.
This supports correct sample routing, scale, bias subtraction and body transform;
it is not independent ground-truth attitude calibration.

## Sensor clock versus host clock

| Measurement | OpenIMU | Original SPI |
| --- | ---: | ---: |
| Valid recorded samples / host second | 792.9317 Hz | 792.0410 Hz |
| OpenIMU hardware counter delta | 1,250 us throughout | Not recorded on this path |
| Hardware elapsed time / host elapsed time | 0.9911646 | Not applicable |

The OpenIMU counter advances about 0.884% less elapsed time than the host over
this recording. "1 us per tick" is a nominal hardware time unit, not proof of
an externally calibrated SI clock. This agrees with earlier slow-rotation
observations; it is not a 1,000x unit error or a rollover error.

Sensitivity replay multiplied only the estimator's elapsed sensor time by
`1.008914132`, retaining identical samples, startup bias and filter equations.
Compared with the deployed filter, projected-gravity direction changed by:

- Median: 0.000787 deg.
- p99: 0.019253 deg.
- Maximum: 0.082518 deg during this complete recording.

Policy gyro values are not multiplied by integration dt and are unchanged by
that replay. These results do not support blaming the observed standing
oscillation primarily on the small clock-scale discrepancy. No clock factor
was applied to deployment. Host-aligned clock calibration would require a
bounded design that separates oscillator drift from queueing and sample loss;
replacing sample time with per-frame USB arrival intervals is not that design.

## Shared latest-state handoff limitation

In the original deployed binaries examined in this audit, acquisition is
nominally 800 Hz, but `NativeImuClient::run()` requests a latest snapshot every **5 ms**
(200 Hz). The 50 Hz actor uses this independently cached snapshot. The actor
does not block waiting for fresh sensor I/O, but its snapshot is not necessarily
the newest sample already acquired by the producer.

| Consumed IMU age at target send | OpenIMU | Original SPI |
| --- | ---: | ---: |
| Median | 3.533 ms | 3.600 ms |
| p99 | 6.411 ms | 6.501 ms |
| Maximum | 7.030 ms | 8.550 ms |

Matching each actor snapshot back to its recorded sensor sample shows a median
of two newer samples already acquired at the controller-state timestamp, p99
four, maximum five, in both runs. Acquisition completion precedes IPC publish
by some processing time; this count is not an exact queue length or publication
latency. Gamepad elapsed-time text is rounded to six significant digits; clock
alignment residuals remain within its decimal precision (at most 0.335 ms).

This is a real, shared handoff-delay opportunity, not evidence that OpenIMU is
slower than SPI. The reported ages exclude unobservable sensor/filter/firmware
latency. There is no automatic backend failover or blending in the tested path.

## Filtering and measured oscillation

Both the inspected OpenIMU firmware and SPI configuration select 800 Hz
low-noise mode, +/-4 g, +/-2,000 deg/s, and UI low-pass setting ODR/4. Both use
the same host six-axis complementary estimator, startup-only gyro bias and
mount matrix `body = [-sensor_z, -sensor_y, -sensor_x]`. Fusion correction is
not added to the gyro observations sent to policy.

Before motor enable, body gyro standard deviations in rad/s were:

| Axis | OpenIMU | SPI |
| --- | ---: | ---: |
| X | 0.001264 | 0.001053 |
| Y | 0.000971 | 0.000956 |
| Z | 0.000924 | 0.000939 |

There is no order-of-magnitude increase in unpowered static gyro noise. During
the initial post-ramp standing interval (powered seconds 6-10), OpenIMU raw
gyro contains clear components around 4, 8 and 12 Hz. The SPI initial standing
interval is much quieter, but its final standing interval also contains a
strong component near 7.5 Hz. The final standing gyro standard deviations are
approximately `[0.0886, 0.1406, 0.1755]` rad/s for OpenIMU and
`[0.0317, 0.0332, 0.0635]` rad/s for SPI.

The oscillation is present in the high-rate raw sensor data, not only generated
by quaternion conversion or timestamp unwrap. That does not determine causal
direction: body motion, module mounting vibration, policy response and joint PD
can form a feedback loop. The recordings had different commanded motion,
starting poses, operator interactions and possible harness support; raw spectra
must not be treated as a controlled sensor-quality comparison. A zero velocity
command is not proof that the robot was motionless or untouched.

The policy takes raw bias-corrected angular rate at 50 Hz with no extra
anti-alias filter before this sampling. The sensor's ODR/4 setting is not a
25 Hz policy-band anti-alias filter. Aliasing of higher-frequency vibration is
a shared hypothesis, not a demonstrated root cause; relevant 5-15 Hz energy
also exists directly in the full-rate raw data. Adding a strong low-pass filter
blindly could increase control delay and should not be bundled with other changes.

The subsequent OpenIMU-first entry and its SPI compatibility option use the
shared client's 1.25 ms request period. See [the follow-up record](IMU_SNAPSHOT800_CANDIDATE_20261124.md); the
measurements in this original audit still describe the earlier 5 ms client.

## Recommended next controlled change

1. Preserve this powered baseline and all gains, limits, scale and mount settings.
2. Prepare an isolated higher-rate asynchronous IMU snapshot client candidate
   (800 Hz rather than 200 Hz), preserving 50 Hz actor and 500/50 Hz motor rates.
   Keep all sensor I/O outside policy and CAN threads and retain freshness gates.
3. Validate timing, disconnect behavior, exclusive backend selection and CPU use
   offline and under zero-gain load before any separately approved powered test.
4. Compare standing with matched posture, harness support and hands-off windows;
   record commanded targets, feedback, gyro/gravity and actual consumed sample
   timestamps. Change one variable at a time.
5. If oscillation persists, distinguish mounting/local vibration and joint
   tracking behavior before proposing anti-alias filtering or stand-control tuning.

No active runtime behavior was changed during this audit, and no audit result
constitutes approval for another powered run.
