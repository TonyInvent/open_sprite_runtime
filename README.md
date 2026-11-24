# Open Sprite Runtime

Canonical repository: [TonyInvent/open_sprite_runtime](https://github.com/TonyInvent/open_sprite_runtime).
## Selected SPI Xbox entry: 800 Hz snapshots (November 24, 2026)

The operator selected the **SPI ICM-45686 + 800 Hz asynchronous snapshot client**
after a successful supervised 120-second Xbox walking test. Walking was reported
normal and no oscillation was observed by the operator in that trial. The native
controller recorded 6,000 policy targets, zero scheduling deadline misses, and
verified all 31 motors disabled at completion. This is a bounded hardware result,
not proof of universal gait improvement or approval for unattended operation.

On the already provisioned Jetson, with battery power, fall arrest, clear space,
and an independent power-cut operator ready:

```bash
cd /home/tony/open_sprite_runtime_openimu
# Offline integrity checks only; no sensor or motor access.
bash run_sprite0825_xbox_imu800_turn120_on_253.sh --check --imu icm-spi
# Explicitly selected SPI backend; supervised powered operation.
sudo bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120 --imu icm-spi
```

| Layer | Selected SPI entry |
| --- | --- |
| Sensor acquisition / software attitude estimator | Nominal **800 Hz**, 1 MHz SPI |
| Asynchronous latest-snapshot requests | Nominal **800 Hz**, 1.25 ms request period |
| Native ONNX policy / ordinary 27 motors | **50 Hz** |
| Host ankle PD / four ankle motor commands | **500 Hz** |
| Native CAN scheduling loop | **2 kHz**, not a per-motor update rate |

Only the snapshot request period changed from 5 ms to 1.25 ms. The model, gains,
limits, sensor filtering, actual-timestamp estimator integration, and CAN binary
are unchanged. Sensor I/O stays outside policy inference and motor control.
Keep still for the initial 15-second calibration; the existing zero-gain preflight
must pass before the powered 120-second schedule begins. LT enables walking
commands; LB+RB held for 3 seconds requests disable. Fall arrest must support the
robot after disable.

The new wrapper defaults to OpenIMU if `--imu icm-spi` is omitted. **Use the
explicit SPI option for the hardware result above.** Both backends share the new
client, but this latest no-oscillation observation is specific to the SPI trial.
The original selector still uses its original 200 Hz snapshot-client actor, and
the original SPI script remains the rollback path:

```bash
cd /home/tony/open_sprite_runtime
sudo bash run_sprite0825_xbox_native_turn120_on_253.sh ENABLE_XBOX_TURN120
```

The new entry requires the separately provisioned, sealed
`candidates/imu_client800_powered_20261124` package and the existing calibrated
baseline. It is not installed just by cloning this repository. See
[snapshot-client validation and deployment record](docs/IMU_SNAPSHOT800_CANDIDATE_20261124.md)
for build tools, prerequisites, the earlier small-step report, and the successful
follow-up. No existing deployment is overwritten by this publication.

## OpenIMU Xbox walking (November 24, 2026)

The OpenIMU integration preserves the stable **50 Hz ordinary-joint / 500 Hz ankle** Xbox
runtime. The new `run_sprite0825_xbox_imu_turn120_on_253.sh` selector defaults to
OpenIMU raw-six-axis CAN FD; `--imu icm-spi` delegates to the original SPI entry.
The old scripts, actor, gains, motor controller and safety limits are unchanged.
This is not the all-motor-500 Hz experiment. See
[OpenIMU integration and commissioning](docs/OPENIMU_MIXED_RATE_XBOX.md) for
protocol, timestamps, installation, offline checks and the qualification status.

One supervised **120-second powered Xbox session completed successfully** on
November 24. The operator confirmed walking; the controller recorded zero
deadline misses and verified all 31 motors disabled at completion. This is a
bounded commissioning result, not unrestricted or unattended walking approval.

On the already provisioned Jetson, use the separate OpenIMU deployment:

```bash
cd /home/tony/open_sprite_runtime_openimu
# Default: OpenIMU CAN FD, with the original policy and motor parameters.
bash run_sprite0825_xbox_imu_turn120_on_253.sh ENABLE_XBOX_TURN120
# Alternative: the original ICM-45686 SPI entry, including its power-management setup.
sudo bash run_sprite0825_xbox_imu_turn120_on_253.sh ENABLE_XBOX_TURN120 --imu icm-spi
```

Keep still for the first 15 seconds of gyro-bias calibration. An 8-second
zero-gain preflight follows; these phases are outside the powered 120 seconds.
The powered schedule is 0-10 s standing, 10-110 s LT-rearmed forward/turn control,
then a final standing interval and disable at 120 s. Forward is limited to
0.10 m/s, turning to +/-0.10 rad/s; reverse is blocked. Release LT to stop the
walking command. Hold LB+RB for 3 seconds to request immediate disable. Fall
arrest, a clear movement area and an independent power-cut operator are required.

OpenIMU uses a dedicated PCAN-USB FD interface named `spriteimu0`, configured at
1 Mbit/s arbitration / 5 Mbit/s data. The linked guide covers persistent naming,
explicit interface bring-up after reboot, receive-only tests and SPI rollback.
These commands require the existing calibrated baseline deployment; cloning
this repository alone does not install the external G74 deployment package.

Safety-gated Sim2Real runtime work for Sprite0825. The current deployment
candidate is the native-50 Hz G74 `model3000`, qualified after the proximal
shoulder pitch/roll motors were changed to J4340P. Its frozen actor, contract,
and Isaac/MuJoCo qualification evidence are distributed in the external G74
Sim2Real candidate package. G59 `model2999` remains the pre-upgrade rollback
baseline; the qualified 100 Hz `model1050` release remains a teacher and
comparison baseline only.

This repository includes an explicitly acknowledged, finite-duration protected
whole-robot policy loop. Full-weight standing and bounded disturbance recovery
have been admitted on hardware with an independent power-cut operator. A bounded
battery-powered 0.10 m/s stand-walk-stop trial completed on 2026-10-10 with fall
arrest and operator supervision; this is not unrestricted walking qualification.
On October 14 the operator reported repeated successful supervised walks with
the native C++ actor and 200 Hz raw-six-axis software IMU candidate. See the
[native walk development record](docs/NATIVE_WALK40_READINESS_20261014.md)
for qualification scope, remaining limitations and the earlier exit-gate fix.
On October 16, three consecutive supervised 40-second ICM45686 walks completed.
The operator reported disappearance of the previous left-leg straightening
pattern, much straighter travel, and stable starts/stops. Controller reports
confirmed successful completion and all 31 motors disabled after each run.
See the [ICM walking milestone](docs/ICM45686_WALKING_20261016.md) for evidence,
fixed gains, commands, and limitations. BNO055 remains the rollback path.
This remains supervised commissioning, not unrestricted walking approval.
Motor mapping, directions,
mechanical limits, IMU convention, four 500 Hz CAN-FD bus tests, differential
calibrations, watchdogs, and integrated standing gates are recorded as completed
commissioning milestones. Active scripts remain fail-closed and require their
exact acknowledgement token; receive-only inspection tools remain available.

## Timing contract

The current candidate uses native ONNX Runtime CPU inference at **50 Hz**,
an independent native raw-six-axis reader/software estimator at nominal
**800 Hz**, using **OpenIMU CAN FD by default in the new selector** or the
original **ICM45686 over 1 MHz SPI** (about 792 Hz measured),
and a native CAN controller with a **2 kHz scheduling loop**. That scheduler
transmits to **each ankle motor at 500 Hz** and **each other motor at 50 Hz**;
it does **not** update every motor at 2 kHz. Python still prepares and supervises
the run.
The estimator uses actual sample intervals; policy consumes the latest valid
state. Startup requires 15 seconds of stillness for gyro bias estimation.
Gyro observations are raw gyro minus bias, rotated into body coordinates;
projected gravity comes from the software estimator, without magnetometer fusion.
See [software IMU design](docs/BNO055_SOFTWARE_FUSION.md).
The BNO055 rollback uses the same estimator architecture at 200 Hz over I2C.
ICM data has its own validated IPC format; it is not decoded as BNO register data.

The `*_on_253.sh` entries are site-specific commissioning scripts. Their model,
contract, calibration and parity-evidence paths are not a portable deployment
bundle. A fresh installation must provision and validate its own matched inputs;
do not bypass missing evidence checks to run hardware.

See the [October 10 development update](docs/DEVELOPMENT_UPDATE_20261010.md)
and [Xbox Bluetooth pairing and walking control](docs/XBOX_BLUETOOTH_CONTROL.md).
On October 19, supervised Xbox One control was exercised on hardware. The operator
reported normal forward motion, stopping, LB+RB motor disable, and subsequently
low-speed turning. The isolated120-second turning entry limits forward velocity
to0.10m/s and yaw rate to+/-0.10rad/s; reverse remains blocked. LT is required for
motion. LB+RB held3s requests disable, bypassing the final standing interval;
fall arrest and independent power cutoff remain required.
The native gamepad reader uses a separate thread and a bounded latest-state
snapshot; it does not perform joystick I/O inside policy inference or CAN control.
See the [Xbox deployment snapshot](docs/XBOX_DEPLOYMENT_20261019.md) for entries,
test scope and site-specific provisioning requirements.

| Layer | Configured rate | What runs at this rate |
|---|---|---|
| Native policy inference | **50 Hz**, 20 ms | Produces joint targets; receives a latest-state motor snapshot via IPC at 50 Hz. |
| Native software IMU | OpenIMU CAN FD or ICM SPI **800 Hz**, nominal 1.25 ms; BNO rollback **200 Hz**, 5 ms | Independently reads raw six-axis data and estimates gravity; policy consumes the latest valid state. CAN/SPI bitrate and sensor ODR are different quantities. |
| Asynchronous IMU snapshot client | Selected `imu800` entry: nominal **800 Hz**, 1.25 ms; original entries: **200 Hz**, 5 ms | Requests the producer's latest state in a separate thread; the 50 Hz policy only copies the cached result. Not the sensor ODR or estimator integration timestep. |
| Native CAN scheduler | **2 kHz**, 0.5 ms | Services due transmit slots across four buses, drains received feedback and checks the policy target watchdog. Not a per-motor update rate. |
| Host ankle PD / parallel linkage calculation | **500 Hz**, 2 ms | Recomputes ankle motor feed-forward torques from held policy targets and latest joint feedback. |
| Four ankle motors: command and feedback polling | **500 Hz per motor**, 2 ms | Sends MIT feed-forward torque commands with motor-side Kp/Kd zero. The two motors in each pair occupy staggered CAN slots. |
| Other 27 motors: command and feedback polling | **50 Hz per motor**, 20 ms | Sends MIT position/Kp/Kd commands; PD runs inside the motor. Includes hips, knees, waist, arms and head. |
| Damiao drive internal control | **1 kHz**, as specified for this hardware | Runs inside the drive, independently of the host CAN transmit rate. |

All rates above are configured nominal rates, not latency guarantees. Feedback
arrives in response to motor commands and is drained on scheduler iterations;
a 2 kHz receive loop does not make a 50 Hz motor's measurements 2 kHz fresh.
Runtime freshness checks and timing reports remain necessary.

With this 31-motor mapping, nominal command traffic is 1,300 frames/s on each
leg bus (2 x 500 + 6 x 50), 400 frames/s on the left-arm bus, and 350 frames/s
on the right-arm bus: **3,350 transmitted command frames/s in total**, plus
motor replies. CAN-FD uses **1 Mbit/s arbitration and 5 Mbit/s data with BRS**;
these bit rates are distinct from control/update rates. The earlier 500 Hz
per-motor full-bus stress tests are not the normal walking schedule.

The 50 Hz policy target uses a 20 ms zero-order hold, matching both the Isaac
Lab decimation loop and the qualified MuJoCo runtime. The 500 Hz ankle controller
reuses that target with new feedback; it does not invent intermediate policy
targets. Its parallel-linkage torque mapping is computed on the host, not by
raising the policy inference rate.

Implementation: scheduling and slot selection are in
[`sprite_can_shadow.cpp`](native/src/sprite_can_shadow.cpp); the per-motor
500/50 Hz assignment is in
[`export_native_motor_config.py`](tools/export_native_motor_config.py).

The qualified `model1050` actor remains a 100 Hz teacher/baseline and is not the
hardware deployment policy. G74 `model3000` is trained natively at 50 Hz with
a 160 ms observation window. Contract validation rejects a 100 Hz actor when
the runtime is configured for 50 Hz.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m unittest discover -s tests -v
```

Inspect a native-50 Hz candidate contract without touching hardware:

```bash
sprite-runtime inspect \
  --contract <candidate>/deploy/contract.json \
  --runtime-config config/runtime.example.json \
  --hardware-config config/hardware.example.json
```

For a native 50 Hz candidate, run the fail-closed safety scenarios and a host
scheduling probe before any CAN hardware is connected:

```bash
sprite-runtime safety-self-test --runtime-config config/runtime.example.json
sprite-runtime heading-self-test --runtime-config config/runtime.example.json
sprite-runtime timing-probe --duration 10 --state-hz 500
```

Damiao drives do not provide the required periodic disabled-state telemetry
without a request frame. The qualified commissioning gate therefore uses the
native active zero-gain position-echo probe while every motor remains disabled;
velocity, Kp, Kd, and feed-forward torque are all encoded as zero. The hardware
contract requires a 120-second report with complete feedback, zero timing/CAN
errors, and zero nonzero-command, enable, or mode-switch attempts. The older
listen-only receiver remains useful only when another approved controller is
already producing bus traffic.

The separate heading-controller implementation follows Isaac Lab's PM01 command interface: while
walking straight it computes `wz = clip(0.5 * wrap(target_yaw - imu_yaw),
-0.2, 0.2)`. Standing resets the target to the current integrated IMU yaw;
manual yaw-rate commands are passed through and the new heading is held when
the operator releases the turn command. Global yaw remains outside the actor.
This controller is **not wired into the current native powered-policy path**.
That path resets and logs relative gyro heading at session startup without
altering actor observations or applying automatic yaw correction. Resetting
the origin is not gyro bias calibration and does not guarantee drift bounds.

Replay a MuJoCo observation trace through the exported ONNX actor. This mode
never opens a CAN interface and checks that runtime inference reproduces the
actions recorded by the qualified simulator:

```bash
sprite-runtime replay-trace \
  --contract <candidate>/deploy/contract.json \
  --trace <candidate>/evaluation/mujoco_matrix/straight_60s_trace.json \
  --sample-stride 10
```

See [Sim2Real plan](docs/SIM2REAL_PLAN.md), [timing](docs/TIMING.md), and
[hardware contract](docs/HARDWARE_CONTRACT.md). The candidate evidence and
remaining blockers are summarized in [G60 model3450](docs/G60_MODEL3450.md),
including the [robust heading audit](docs/G60_ROBUST_HEADING_AUDIT.md).
The four-motor proximal-shoulder upgrade is documented in
[Sprite0825 4340P shoulder revision](docs/SPRITE0825_4340_SHOULDER_REVISION.md);
the receive-only Damiao frame contract and pinned manufacturer sources are in
[Damiao protocol source audit](docs/SPRITE0825_DAMIAO_PROTOCOL_SOURCE_AUDIT.md).
G74 model3000 is the frozen software candidate after independent-seed Isaac
qualification and the unchanged seven-case MuJoCo gate matrix. G59 model2999
remains the pre-upgrade rollback baseline.

The provisional Yahboom 9-axis pelvis IMU mount, frame transform, read-only
serial capture, and hardware-arrival checklist are documented in
[Sprite0825 Yahboom IMU integration](docs/SPRITE0825_YAHBOOM_IMU_INTEGRATION.md).
The Jetson's existing high-performance CH340 driver is a prerequisite and is
not modified by this project.

Synchronized raw CAN, policy, motor, temperature, and IMU logging for physical
parameter identification is documented in
[Sprite0825 real-data system identification](docs/SPRITE0825_REAL_DATA_SYSTEM_IDENTIFICATION.md).

## License

GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).
