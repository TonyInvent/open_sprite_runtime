# OpenIMU for the stable mixed-rate Xbox runtime

## Scope and status

**The primary runtime is OpenIMU CAN FD at nominal 800 Hz with an 800 Hz
asynchronous snapshot client.** Use `run_sprite0825_xbox_imu800_turn120_on_253.sh`
for this path; it defaults to OpenIMU. Future development prioritizes OpenIMU.
SPI remains an explicit compatibility/rollback/comparison option, not a promise
of equal feature updates. The original selector without `800` in its filename
retains the earlier 200 Hz snapshot client. See
[the shared-client update](IMU_SNAPSHOT800_CANDIDATE_20261124.md) for prerequisites
and backend-specific evidence. The earlier commissioning records below retain
the rates and commands actually used at the time.

This candidate starts from `4515206c24404e18a2d5c168eccdb7468aea6ab7`, not
the experimental `xbox_500hz` branch. It adds an IMU selector around the existing
sealed Xbox turn120 admission. The original entry scripts and installed control
binaries are not overwritten. Hardware qualification of this combination is
separate from the previously tested MacMimic runtime. On November 24, 2026,
this integration completed its first supervised 120-second powered Xbox walk;
the operator confirmed walking and all 31 motors were verified disabled at
completion. See the powered evidence section below for the exact scope.

The canonical repository is
[TonyInvent/open_sprite_runtime](https://github.com/TonyInvent/open_sprite_runtime).
Keep the existing baseline deployment
intact when installing this additive selector.

| Component | Unchanged rate / behavior |
| --- | --- |
| G74 model3000 native ONNX policy | 50 Hz |
| Ordinary joint motor commands (27 motors) | 50 Hz, motor-internal PD |
| Ankle motor commands (4 motors) | 500 Hz, existing host-side joint PD and parallel torque mapping |
| Native CAN scheduler | 2 kHz scheduling loop, not 2 kHz per motor |
| Xbox controls | Existing LT rearm, forward 0..0.10 m/s, turn +/-0.10 rad/s, LB+RB disable |
| Session | Existing 120 s schedule including final standing interval |
| IMU | OpenIMU nominal 800 Hz by default; original SPI ICM-45686 selectable |

No model, observation order, gain, torque cap, joint limit, ankle/head mapping,
motor zero, or timing watchdog is changed. This is not a training change.

## Reference and wire contract

Ported from [TonyInvent/MacMimic](https://github.com/TonyInvent/MacMimic/tree/bc7be0a5868f85bbe1f3dc9a4a7c9de3a99788d9/runtime),
commit `bc7be0a5868f85bbe1f3dc9a4a7c9de3a99788d9`, under AGPL-3.0:
`native/icm45686/openimu.{hpp,cpp}`, decoder/vcan tests and adapter discovery.
The receiver is built as a separate `sprite_openimu` executable. The SPI binary
is not rebuilt or replaced for deployment.

- Dedicated PCAN-USB FD (`0c72:0012`), now named `spriteimu0` on 253.
  Discover by USB identity, not by assuming its Linux interface number.
- Arbitration 1 Mbit/s; data 5 Mbit/s; standard ID `0x001`, CAN FD with BRS,
  exactly 16 bytes, big-endian words.
- Bytes 0..1: unsigned 16-bit hardware timestamp in microseconds.
- Bytes 2..7: signed int16 accelerometer XYZ, +/-4 g.
- Bytes 8..13: signed int16 gyroscope XYZ, +/-2000 degrees/s.
- Bytes 14..15: raw signed temperature count, retained in evidence.
- Nominal timestamp increment: 1250 us (800 Hz). Unsigned subtraction unwraps
  the 65.536 ms counter. Duplicate ticks, regressions appearing as large jumps,
  gaps of 30 ms or more, malformed frames and socket overflows stop acquisition.
- Mount remains sensor X down, Z back: body vector = `[-sensor_z, -sensor_y, -sensor_x]`.

The firmware must already provide this exact scale, format and mount. Raw frames
do not self-describe their scale. The host does not silently reconfigure firmware
or infer new axis signs. Validate stationary gravity and hand-tilt directions
before using a new hardware/firmware build.

The estimator integrates using **hardware sample intervals**, not USB arrival
intervals. Kernel RX timestamps are converted to monotonic host time for IPC
freshness checks, with the reference's 2% clock-drift allowance. This estimates
transport backlog relative to earliest arrivals; it does **not** measure constant
sensor/filter or firmware latency or synchronize the two clocks absolutely.
There is no magnetometer, startup leveling, or fabricated fresh timestamp.

The same six-axis filter and 15 s stationary gyro-bias window produce `icm-v3`
(`SPIMU003`) latest-state IPC. Policy angular velocity remains raw gyro minus
startup bias, transformed into body coordinates; attitude correction is not
added to policy gyro. The independent native receiver and native actor/CAN
processes remain separate. Python only orchestrates startup and reports.

## Installation on the prepared Jetson

The additive deployment directory is `/home/tony/open_sprite_runtime_openimu`.
It uses the existing `/home/tony/open_sprite_runtime` deployment, its virtualenv,
local calibration, sealed G74 actor and CAN binaries. It is not a standalone
replacement for the baseline deployment.

To obtain the source without overwriting an existing deployment:

```bash
git clone https://github.com/TonyInvent/open_sprite_runtime.git /home/tony/open_sprite_runtime_openimu
```

Use this clone command only when that destination does not already exist. A
fresh robot must separately provision the G74 model3000 actor/contract, baseline
candidate binaries and parity evidence, motor bus mapping/protocol ranges,
joint directions/zeros, left/right ankle and head differential calibration,
mechanical limits, IMU mounting, Xbox mapping and controller realtime capability.
The site-specific launchers do not download or substitute those prerequisites.

```bash
cd /home/tony/open_sprite_runtime_openimu
bash build_sprite0825_openimu_on_253.sh
bash run_sprite0825_xbox_imu_turn120_on_253.sh --check
```

The build and `--check` do not access CAN/SPI. `--check` verifies the existing
baseline qualification seals as well. No new `setcap` is needed for the unchanged
CAN controller.

Configure **only the dedicated OpenIMU link**, explicitly:

```bash
cd /home/tony/open_sprite_runtime_openimu
sudo /home/tony/open_sprite_runtime/.venv/bin/python tools/openimu_interface.py --up
```

Discovery refuses `kcan1`..`kcan4`, unknown USB adapters and ambiguous matches.
It will not cycle an already-UP link to change its rate. The motor links still
use their original setup script and are not changed by IMU setup.

## Receive-only commissioning

```bash
cd /home/tony/open_sprite_runtime_openimu
bash run_sprite0825_xbox_imu_turn120_on_253.sh --imu-only --duration 60
```

Keep the IMU stationary for the first 15 seconds. The requested duration is the
subsequent observation interval, not the calibration interval. This mode opens
only the dedicated IMU CAN receiver and local IPC; it sends no CAN frames and
does not start policy or motor control. CSV, producer log and `session.json` are
saved under this deployment's `reports/xbox_openimu_*` directory.

For a 120-second dynamic attitude check on the Jetson desktop:

```bash
cd /home/tony/open_sprite_runtime_openimu
bash review_sprite0825_openimu_mujoco_on_253.sh 120
```

Keep still for 15 seconds, then wait for `VIEW_READY`. Slowly tilt forward/back,
lean left/right, and turn left/right, returning to the starting pose between
axes. Observe matching directions in MuJoCo. This uses the existing neutral-joint
model for attitude display only: it is not joint feedback or a policy rollout.
Roll and pitch retain physical tilt; six-axis yaw is relative, not magnetic north.
The 120 seconds begin when the window opens, excluding calibration. The active
desktop must be logged in and accessible to `tony`. An existing `DISPLAY` is
respected; otherwise a single X socket is selected, never an arbitrary display.

The renderer runs as a separate child process under the receive-only launcher.
Window closure, errors and signals clean up its bounded native IMU producer;
nonzero viewer exit (including a crash) fails the session. `viewer.json`,
`viewer.csv`, `viewer.log`, and the raw IMU capture are retained together.
No motor CAN frames, policy execution or motor enable occurs in this path.

Next, with the robot supported and all motors powered but disabled, the existing
zero-gain preflight is available:

```bash
bash run_sprite0825_xbox_imu_turn120_on_253.sh --preflight-only
```

Unlike `--imu-only`, **preflight transmits zero-gain motor polling frames**.
Do not describe it as receive-only. It performs the unchanged readiness checks.

## Powered use after qualification and onsite approval

### No-display alternative: compare against the original SPI IMU

When both IMUs are rigidly attached to the same body with sensor X down and Z
back, use the terminal-guided comparison instead of MuJoCo:

```bash
cd /home/tony/open_sprite_runtime_openimu
sudo bash compare_sprite0825_openimu_spi_on_253.sh
```

Press ENTER when stationary. Both independent native producers calibrate for
15 seconds; wait for `BOTH_READY`. The subsequent 56-second schedule prompts
stillness, forward/back pitch, rest, left/right roll, rest, left/right yaw, and
final stillness. Use small, slow excursions and return to the starting pose
between axes. Keep the robot mechanically supported. No motor needs enabling.

Only the existing SPI sensor is configured using its unchanged 800 Hz capture
binary; OpenIMU is receive-only. The wrapper temporarily holds SPI runtime PM
on and restores its previous setting. It never configures the motor CAN buses,
starts policy, transmits motor frames, or changes motor zero. No graphics or
display access is involved.

Reports under `reports/dual_openimu_spi_*` contain native-rate raw captures from
both IMUs, their logs and a monotonic-clock phase timeline. `acquisition_completed`
only means the scripted capture completed; `direction_verified` remains false
until the measurements and the operator's movement are reviewed. Compare both
positive and negative excursions, not only a near-zero net angle after returning
to the starting pose. The two IMUs are comparison instruments, not independent
ground truth; unknown mounting mismatch and body flex must be considered.

### Walking entry

Primary OpenIMU, after provisioning the reviewed 800 Hz snapshot candidate:

```bash
cd /home/tony/open_sprite_runtime_openimu
bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120
```

Explicit SPI compatibility test with the same 800 Hz snapshot client:

```bash
sudo bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120 --imu icm-spi
```

The 800 Hz candidate uses the original SPI producer and an isolated copy of the
reviewed power-management wrapper. The earlier selector without `800` still
delegates directly to the original SPI entry. There is
**no automatic IMU failover** during a session. OpenIMU loss stops its producer;
existing policy freshness/watchdog checks and whole-body disable handling remain
active. There is no motor enable before successful readiness checks. A physical
fall arrest, clear arm/walking area and independent power safety operator remain
required. Stop other IMU/runtime programs before either path. Do not run both
old and new launchers concurrently.

The original command remains unchanged and still selects SPI:

```bash
cd /home/tony/open_sprite_runtime
sudo bash run_sprite0825_xbox_native_turn120_on_253.sh ENABLE_XBOX_TURN120
```

## Offline validation

Offline validation completed on November 24, 2026:

- All 3 C++ tests passed in WSL (GCC 13.3) and on Jetson 253 (GCC 11.4).
- The final 22 Python tests passed on Jetson 253, covering selection, interface
  identity, naming safeguards, viewer transforms and dual-IMU analysis.
- WSL vcan integration passed with 12,002 samples, completed stationary bias,
  valid `SPIMU003` IPC, and the expected stream-timeout failure after stopping TX.
- Both IMU selector `--check` paths passed on 253, including the original
  baseline qualification seals.
- Initial inspection identified the dedicated PCAN as `kcan5`, USB path
  `1-2.3`, while DOWN. It was subsequently configured and renamed `spriteimu0`.
- No physical CAN frames, motor enable or powered tests were issued in this
  qualification stage. Virtual test traffic is not physical CAN traffic.
- The original stable entry SHA-256 remains
  `351052a6175463bd495caeafedd5b3226580a94e55f8400b443a76bb210db792`;
  the stable CAN executable remains
  `43cebcd735c083844e5f83b9b23c11cf38877489f29def977efad43094f7338e`.

### First physical receive-only capture

The operator subsequently completed `xbox_openimu_wiqilr7w` using `--imu-only`.
Its report passed with no errors. A local copy is retained for analysis.

- 59,755 frames over 75.359 host seconds, including calibration; 792.930 Hz
  measured against the host clock. Every hardware timestamp increment was
  exactly 1,250 us (nominal 800 Hz), across 1,140 counter wraps. No timestamp
  gap or duplicate was observed; the sensor and host clocks are not identical.
- Kernel RX gap: p99 1.340 ms, maximum 2.049 ms.
- Kernel RX to userspace read: p99 0.063 ms, maximum 6.727 ms; maximum interval
  between userspace reads 7.970 ms. This is not a hard-real-time guarantee.
- 2,958 IPC checks over the subsequent 60 s, no repeated sequence, maximum
  estimated sample age 2.181 ms. This is a diagnostic client, not a loaded actor.
- Mean bias-corrected body gyro: approximately
  `[-2.14e-5, 2.47e-5, -1.51e-5]` rad/s. Acceleration magnitude mean 9.782 m/s^2.
- Mean estimated body attitude: roll +4.059 deg, pitch +7.406 deg, total tilt
  8.440 deg. Horizontal projected-gravity norm 0.14677 exceeds the **unchanged**
  startup gate of 0.10. Confirm the physical pose/mount and level the body before
  motor preflight; do not reset attitude to hide this tilt.
- `producer_exit=1` accompanied `producer_stopped_by_launcher=true`: the launcher
  intentionally sent SIGTERM after the receive-only interval; there was no
  producer error in its log. This is not a motor shutdown result.
- Raw CSV SHA-256:
  `f0de911a9706842b2dee52f74716cf2f259025da44c00cae99db6c58ca685741`.

Run `tools/analyze_openimu_capture.py REPORT_DIRECTORY` to reproduce the timing
audit. It writes `timing_audit.json` without accessing hardware.

At this initial receive-only milestone, hardware work still needed mounting/direction checks, full-chain zero-gain preflight,
then separately authorized powered walking. Static data alone does not establish
correct dynamic axis response or end-to-end latency under motor/policy load.

### Dual-IMU dynamic comparison

The operator completed `dual_openimu_spi_m7oqkr68` on November 24. Acquisition
finished without errors: 56,494 OpenIMU samples and 56,446 SPI samples. No motors
were accessed. Both producer exits were requested by the diagnostic launcher.

Host-aligned, bias-corrected body angular velocity comparison:

| Prompted phase / compared axis | Correlation | SPI / OpenIMU fitted amplitude |
| --- | --- | --- |
| Pitch / Y | 0.999930 | 0.998544 |
| Roll / X | 0.999908 | 0.999552 |
| Yaw / Z | 0.999994 | 1.002733 |

The measurements support matching body-axis signs and near-equal angular-rate
scale. Motion was not purely single-axis: the pitch phase also contained
substantial yaw. This does not establish independently measured absolute angles.
The diagnostic three-axis fit is close to identity and is **not** applied as a
new calibration matrix.

All OpenIMU hardware timestamp increments were 1,250 us, with no gaps or repeats.
Its maximum kernel RX gap was 2.060 ms and maximum kernel-RX-to-read delay
0.528 ms (p99 0.039 ms). SPI discarded 3 late samples; maximum valid sample gap
was 2.525 ms and edge-to-read completion 1.205 ms. These measurements have
different origins and do not prove one sensor's total physical latency is lower.

The +/-50 ms relative alignment scan selected 0 ms on a 1 ms grid for all three
axes. Slow manual movement cannot resolve sub-millisecond or intrinsic filtering
delay, and this is not full policy/motor-load qualification.

Yaw-axis gyro-integral excursion was 111.481 deg using OpenIMU sensor time versus
112.799 deg using SPI host DRDY time (about 1.17% difference). Integrating the
same OpenIMU angular rates using its host timeline gives 112.479 deg. Thus much
of this difference is the observed sensor/host timebase difference, not an axis
sign error. These are body-axis integrals, not exact Euler yaw for coupled
motion. No automatic scale, clock, bias or mount correction was introduced.

Initial stationary accelerometer tilt was approximately OpenIMU roll/pitch
0.915/1.610 deg versus SPI 0.825/1.899 deg. At the final rest it was 2.456/9.311
versus 2.340/9.641 deg. Both sensors agree that the final body pose is pitched;
level and support the robot before the unchanged motor preflight. Do not force
the IMU attitude to zero to conceal the physical pose.

Reproduce with `tools/analyze_dual_openimu_spi.py REPORT_DIRECTORY`. The separate
`comparison.json` retains input hashes, all phase statistics, positive/negative
integrals and limitations; the original capture report is not rewritten.
At this dual-IMU comparison milestone, full-chain zero-gain preflight and
powered qualification were still pending; subsequent results are recorded below.

```bash
python3 -m unittest discover -s tests -p 'test_openimu_*.py' -v
bash build_sprite0825_openimu_on_253.sh
```

### Mixed-rate startup preflight: November 24, 2026

Session `xbox_openimu_wcsgd31m` passed the unchanged 8-second startup preflight
using OpenIMU on `spriteimu0`. Calibration preceded the motor shadow. All 31
motors had 100% feedback coverage: 400 TX/RX per ordinary motor and 4,000 TX/RX
per ankle motor. Native CAN recorded zero deadline misses, maximum scheduling
lateness 0.023721 ms, zero enable attempts and zero nonzero-gain/torque TX attempts.
The projected-gravity horizontal norm peaked at 0.062227, below the unchanged
0.10 gate. The startup torque and readiness gates passed.

This existing preflight runs Python ONNX inference with native CAN, not the
native powered actor: 400 policy states/targets, mean inference 2.001468 ms and
maximum 6.330084 ms. The CAN-side target count was 399 (99.75% coverage), which
passed its existing gate. IMU maximum age at receiver delivery was 1.618273 ms;
this is not end-to-end inference age or intrinsic sensor latency. The native
powered actor and powered OpenIMU walking remain untested in this session.

Compatibility logs retain legacy BNO/ICM source labels and a GPIO timestamp
description. They do not describe the actual OpenIMU transport: this session's
source is PCAN CAN FD, sensor hardware ticks and kernel receive timestamps,
carried over the existing `icm-v3` IPC format. The sensor producer subtracts
stationary gyro bias; a legacy consumer field must not be interpreted as proof
that producer bias correction is absent.

Reports and the replayable trace were copied to Windows under
`work/openimu_review_20261124/xbox_openimu_wcsgd31m`. The baseline entry/controller
hashes remain unchanged and the resolved controller retains `cap_sys_nice=ep`.
All test processes exited. No powered session was started.

### First supervised powered Xbox session: November 24, 2026

Session `xbox_openimu_n7ive8fc` used the default OpenIMU selector and unchanged
mixed-rate baseline after explicit onsite approval. Static calibration and the
zero-gain readiness gate passed, followed by the full 120-second powered run.
The operator reported that the robot walked. Native actor and controller both
exited successfully; the launcher reported `POWERED_COMPLETION_VERIFIED`.

| Recorded item | Result |
| --- | --- |
| Controller report | `native_protected_policy_admission_icm_20261124_143940.json` |
| Actor report | `native_protected_policy_actor_icm_20261124_143940.json` |
| Powered duration | 120.000000 s |
| Native policy states / controller targets | 6,001 / 6,000 |
| Actor console compute mean / maximum | 0.326864 / 2.3165 ms |
| Controller deadline misses | 0 |
| Maximum controller scheduling lateness | 0.043857 ms |
| Ordinary-motor command count | 6,000 per motor (50 Hz) |
| Ankle-motor command count | 60,000 per motor (500 Hz) |
| Final disabled verification | All 31 motors |
| Controller errors | None |
| Automatic mode switch / motor zero reset attempts | 0 / 0 |

The first 15-second stationary calibration and 8-second zero-gain preflight are
outside the powered duration. The initial preflight still uses Python ONNX;
the powered actor is native ONNX. Legacy report filenames contain `icm` because
the original sealed entry was reused, not because SPI supplied this session.
The session records the actual source as OpenIMU on `spriteimu0`.

Raw capture, session/admission logs and controller/actor reports are backed up
locally under `work/openimu_review_20261124/xbox_openimu_n7ive8fc`. Raw hardware
captures are not bundled into this source release. This single session does not
prove improved gait versus SPI, unrestricted operation, or long-term reliability.
Do not change control gains, safety gates or sensor scales on that basis.

### Persistent OpenIMU interface name

The Jetson's existing `100-kcan.rules` names every interface using the `kcan`
driver by enumeration number. The PCAN adapter also uses that driver on this
machine, so `kcan5` or `can3` is not a persistent hardware identity.

Install the dedicated name while the IMU link is DOWN and all runtime sessions
are stopped. This does not reconfigure `kcan1` through `kcan4` or transmit motor
commands. The installer refuses an active-link rename, a name collision, or an
existing rule with different contents.

```bash
cd /home/tony/open_sprite_runtime_openimu
sudo python3 tools/install_openimu_name.py --apply
```

The rule assigns `spriteimu0` using PCAN VID/PID `0c72:0012` and the detected
physical USB port (currently `1-2.3`); no unique USB serial was exposed. Keep
this adapter on the same USB port. A port change requires reviewing/rebinding
`/etc/udev/rules.d/90-sprite-openimu-net.rules`. The runtime still verifies USB
identity instead of trusting the interface name alone. Rule installation is
persistent; link UP and bitrate configuration are not made automatic at boot.
After reboot, use the dedicated setup command as well as the motor-bus setup:

```bash
cd /home/tony/open_sprite_runtime_openimu
sudo python3 tools/openimu_interface.py --imu-can-interface spriteimu0 --up
```

The installer brings up the IMU at 1 Mbit/s arbitration / 5 Mbit/s data for the
current session. Neither command starts policy execution or enables motors.
The naming mechanism uses udev's final `NAME:=` assignment (udev >=247), as
documented in https://www.freedesktop.org/software/systemd/man/latest/udev.html.

The vcan integration test can run only on a separately created **virtual** CAN
FD interface. It refuses physical CAN links. It exercises 15 s calibration,
latest-state IPC and stream-loss failure without touching motors:

```bash
python3 native/icm45686/test_openimu_vcan.py build/openimu/sprite_openimu spriteimu_test
```
