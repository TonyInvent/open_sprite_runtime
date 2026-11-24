# Shared 800 Hz IMU snapshot client candidate

## Current status

**OpenIMU CAN FD with 800 Hz acquisition and 800 Hz snapshot requests is the
primary runtime and ongoing development path.** SPI is a compatibility,
rollback, and comparison backend, not the preferred deployment. Future updates
may be OpenIMU-specific; equivalent SPI feature development is not promised.

The SPI compatibility entry completed the successful supervised
120-second follow-up at `20261124_182201`. The operator reported normal walking
and no observed oscillation. Controller and actor reports both passed, with
6,001 states, 6,000 targets, zero scheduling deadline misses, maximum lateness
0.037876 ms, and all 31 motors verified disabled at completion.

This supersedes the earlier SPI gait-regression hold for continued supervised
use on this commissioned robot. It does not prove why the earlier small-step
trial differed, quantify a general performance improvement, or qualify both
backends equally. The earlier evidence and limitations remain below.

## Scope

Both SPI ICM-45686 and CAN-FD OpenIMU use the same `icm-v3` packet client.
The independent client thread now requests the producer's latest snapshot at a
nominal 1,250 microsecond interval, previously 5,000 microseconds. This changes
neither sensor ODR nor estimator integration. Non-ICM legacy clients retain their
5,000 microsecond interval. OS scheduling means requests need not achieve exactly
800 per second; measure actual intervals under full load.

There is one selected IMU per session, not blending or automatic failover.
Policy remains 50 Hz, ordinary motors 50 Hz, ankle motor control 500 Hz, and CAN
scheduling 2 kHz. Sensor scale, installation rotation, bias handling, estimator,
timestamp conversion, PD, command limits, and watchdogs are unchanged. The
25 ms IPC timeout and 30 ms sample-age checks are not relaxed. Policy snapshots
only copy mutex-protected cached state; they do not perform blocking sensor I/O.

## Isolation and deployment status

The qualified baseline in `/home/tony/open_sprite_runtime` is not modified.
The existing OpenIMU selector and its SPI fallback still launch the original
200 Hz snapshot-client actor. They must not be described as running this new
candidate merely because the shared source header has changed.

The isolated build is staged at:

```text
/home/tony/open_sprite_runtime_openimu/candidates/imu_client800_20261124_v2
```

It contains the candidate actor, fake-peer actor, offline replay executable,
copied build inputs, and qualification results. No new powered entry is installed
by the qualifier. The older failed build directory is retained for audit.

`tools/qualify_imu_client800.py` checks the baseline seal and verifies that the
shared header differs only by the snapshot period change. It builds using the
deployed actor source, keeping all motor and policy logic unchanged. The modified
header is placed beside that source so quoted-include resolution cannot silently
select the old header. Baseline source hashes and candidate hashes are recorded.

## Validation

`native/icm45686/client_test.cpp` uses UNIX socket fake peers only. It checks:

- The common icm-v3 interval is 1,250 microseconds; legacy interval is 5,000.
- Snapshot values exactly match validated producer data without extra filtering.
- Freeze, IPC silence, malformed packets, and sequence regression are rejected.
- Policy-rate snapshot age and actual request rate are reported separately.

The actor qualification reuses the existing 6,001-frame, 120-second synthetic
Xbox fixture and its freeze, state-disconnect, and operator-disable cases. It
checks byte-exact offline replay of consumed observations and equality between
computed protected targets and transmitted fake IPC targets. It never opens CAN,
SPI, or a real joystick. A synthetic-device environment is necessary even for
the fake actor; the initial attempt stopped with zero frames because this
environment was missing. This was a test harness setup failure, not hardware
evidence.

Completed offline results on 2026-11-24:

- Native IMU CTest suite: 4/4 passed on WSL, including SPI packet and OpenIMU tests.
- Jetson shared-client fake-peer test: passed. One run observed about 763 requests/s,
  median snapshot age 0.673 ms and maximum 1.343 ms at 50 Hz consumption. This is
  synthetic IPC timing, not sensor intrinsic latency or a full-load guarantee.
- Jetson full actor: 6,001 frames in the 120-second fixture; byte-exact replay and
  protected-target equality passed. No state round trips exceeded 20 ms; maximum
  was 3.273 ms. Freeze, state disconnect and operator-disable cases all passed.
- The original powered candidate seal still passes after the build and tests.

The report is `qualification.json` in the isolated candidate directory. Its
`powered_qualified` value remains false. No actual IMU or motor was accessed by
these qualification runs.

## Completed real-feedback shadow qualification

Both backends passed separate 120-second zero-gain runs on 2026-11-24 after
onsite confirmation of support and powered-but-disabled motors. Each producer
ran for 150 seconds, including its initial 15-second stationary calibration.
The OpenIMU producer exited before the SPI producer started. No enable, mode
switch, zero reset, or nonzero impedance/torque command was sent.

| Metric | OpenIMU CAN FD | SPI ICM-45686 |
| --- | ---: | ---: |
| Policy frames / targets | 6,000 / 6,000 | 6,000 / 6,000 |
| Consumed IMU age median | 1.706 ms | 1.742 ms |
| Consumed IMU age p99 | 2.836 ms | 3.027 ms |
| Consumed IMU age maximum | 4.045 ms | 4.953 ms |
| Inference-path maximum | 2.457 ms | 1.795 ms |
| CAN scheduler deadline misses | 0 | 0 |
| CAN scheduler maximum lateness | 0.0355 ms | 0.0362 ms |
| Offline replay byte-exact | Yes | Yes |

All 31 motor sample coverages were 100%. Each ordinary motor sent/received
6,000 frames, and each ankle motor sent/received 60,000 frames, confirming the
unchanged mixed-rate control transport. The shadow actor computes the full
policy and protection pipeline but zeros velocity, Kp, Kd and feedforward in
the IPC targets. This run used stand commands, not live Xbox inputs. The separate
offline powered-actor tests cover the Xbox path; this is not a powered walking
qualification or full nonzero ankle-torque workload measurement.

OpenIMU delivered 118,937 samples over 150 seconds, approximately 792.91 Hz in
host time, with median hardware timestamp delta 1,250 us. Maximum kernel RX
gap was 2.073 ms, and maximum estimated sample age at read was 1.101 ms.
SPI recorded 118,819 samples, one missed/coalesced event, and seven late-sample
discards. Its maximum accepted sample gap was 2.538 ms. No gates were relaxed.

The earlier powered baseline had median consumed ages around 3.5-3.6 ms. The
new shadow figures are consistent with reduced software snapshot handoff delay,
but these are different runs and loads, not a controlled powered A/B comparison.
None of these age metrics includes unobservable intrinsic sensor/filter delay.
Standing oscillation improvement remains unproven until a powered comparison.

Reports on 253:

```text
/home/tony/open_sprite_runtime_openimu/reports/imu_client800_openimu_dmwjye7_
/home/tony/open_sprite_runtime_openimu/reports/imu_client800_icm-spi_kbuupiep
```

Both complete report directories, raw captures, consumed observations, replay
outputs, and the exact acquisition runner were backed up to Windows as
`imu800_shadow_evidence_20261124.tar.gz`. The SHA-256 was verified on both hosts:
`d2e767024313fd32ef13148fc26bf86939f2063764ca6be25b267a8299cadea6`.

The isolated shadow build is `candidates/imu_client800_shadow_20261124` under
the same additive root. It is compiled with `SPRITE_SHADOW_LOOP`, not powered
mode. Its fake-peer tests verify that every emitted IPC target has zero velocity,
Kp, Kd and feedforward, while recorded computed targets still match offline replay.

Repeat only with support, powered-but-disabled motors, and a stationary start:

```bash
cd /home/tony/open_sprite_runtime_openimu
bash qualify_sprite0825_imu800_shadow_on_253.sh --imu openimu --check
bash qualify_sprite0825_imu800_shadow_on_253.sh --imu openimu --duration 120 \
  --confirm ZERO_GAIN_IMU800_ALL_DISABLED_SUPPORTED
sudo bash qualify_sprite0825_imu800_shadow_on_253.sh --imu icm-spi --duration 120 \
  --confirm ZERO_GAIN_IMU800_ALL_DISABLED_SUPPORTED
```

SPI uses the existing PM lock and requires `power/control=on`. If invoked with
sudo, the wrapper can temporarily set that value and restores it on exit.
No IMU backend is automatically selected as a fallback after a failure.

## Isolated powered comparison entry

Prepared and checked offline on 2026-11-24; no powered test was launched during
preparation. Both backend choices route to the same actor in
`candidates/imu_client800_powered_20261124`. The new entry is opt-in; the existing
`run_sprite0825_xbox_imu_turn120_on_253.sh` still defaults to the original 200 Hz
snapshot client and the original SPI fallback.

The candidate uses copies of deployment parameters. Admission exports target
those copies, not the baseline tables. Offline export and native-bundle checks
confirmed byte-identical motor tables, joint safety limits, kinematics and actor
configuration. The native CAN binary is the original qualified binary. The entry
seal pins the new actor, its four fake-peer results, both successful real-feedback
shadow reports, copied parameters, original baseline hashes, and selector code.
All 24 OpenIMU/selector regression tests passed; both new and both rollback entry
checks passed without hardware access.

After replacing the battery if necessary, and with fall arrest, a clear walking
and arm area, and an independent power safety operator in place, run exactly one:

```bash
cd /home/tony/open_sprite_runtime_openimu
# Default: OpenIMU on the dedicated CAN FD adapter.
bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120

# Alternative: original SPI ICM-45686 producer, same new snapshot client.
sudo bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120 --imu icm-spi
```

Each begins with 15 seconds stationary calibration and the existing 8-second
zero-gain readiness preflight, outside the 120-second powered schedule. The
schedule remains 0-10 seconds standing, 10-110 seconds deliberate LT rearm and
forward/turn control, then ramp to zero and stand until 120 seconds before
disable. Forward speed remains 0..0.10 m/s, turn rate +/-0.10 rad/s; no reverse.
LB+RB held for three seconds requests disable, and fault shutdown is unchanged.
Fall arrest must support the robot after disable; a zero velocity command is
not proof of stable standing.

Use `--check` in place of `ENABLE_XBOX_TURN120` for offline seals only. SPI
requires sudo for the unchanged scoped power-management wrapper. Neither
backend performs automatic failover or combines measurements from the other.

The next gate is the onsite powered comparison, not another claim of qualified
gait. Match posture, harness support and hands-off standing windows. Preserve
the zero-gain evidence and requalify after further code or configuration changes.

Offline passing does not establish reduced physical oscillation. The original
scripts remain the rollback path until hardware qualification is complete.

## Powered SPI regression investigation (2026-11-24)

The operator reported substantially smaller steps with the new SPI entry. At
that point the candidate was **not gait-qualified**. Successful zero-gain timing checks and a
completed powered schedule do not establish gait equivalence or improvement.
Keep the original entry available; do not change PD, torque caps, joint limits,
sensor filtering, or estimator gains to compensate for an unexplained regression.

The follow-up investigation used saved evidence only. It did not enable motors,
read live sensors, or launch another powered test. Analysis files on Windows are
under `work/openimu_review_20261124` in the investigation workspace:

- `audit_small_steps.py` and `small_steps_audit.json`: commands, timing, joint
  excursions, raw sensor cadence, and exact consumed-sample matching.
- `replay_recorded_actor.py` and `small_steps_offline_parity.json`: both recorded
  SPI runs replayed through existing baseline and candidate offline executables.
- `imu800_powered_audit_20261124.tar.gz`: preserved new powered-run evidence.

### Compared SPI runs

| Measurement | Original snapshot client | New snapshot client |
| --- | ---: | ---: |
| Run timestamp | 20261124_145600 | 20261124_162944 |
| Snapshot request period | 5 ms | 1.25 ms |
| Sensor nominal ODR | 800 Hz | 800 Hz |
| Actor records | 6001 | 6001 |
| Median policy state interval | 20.000152 ms | 20.000178 ms |
| Median IMU sample age at actor | 3.59996 ms | 1.80289 ms |
| Maximum IMU sample age at actor | 8.55003 ms | 4.12520 ms |
| Maximum raw sample gap during powered interval | 2.524638 ms | 2.524811 ms |
| Consecutive actor samples repeated/regressed | 0 / 0 | 0 / 0 |
| Longest full-speed straight interval | 21.2023-25.0222 s | 15.4423-28.5823 s |
| Left hip pitch actual excursion | 0.2878 rad | 0.1313 rad |
| Left hip pitch actor target excursion | 0.2957 rad | 0.1794 rad |
| Left knee actual excursion | 0.3793 rad | 0.2374 rad |
| Left knee actor target excursion | 0.3769 rad | 0.2717 rad |

Excursion means the 95th minus 5th percentile within the stated interval, not
Cartesian step length. The intervals have different durations and were not
matched trials. Full-speed straight selection requires vx >= 0.09 m/s and
abs(wz) < 0.01 rad/s. The new SPI run contains three further straight intervals
with similarly reduced left hip excursions (approximately 0.107-0.160 rad).
The command reached 0.10 m/s; inadequate joystick demand does not explain those
intervals. Spectra shift toward higher frequencies, but a joint spectral peak
must not be presented as a measured foot-contact step rate.

### Checks that passed

- All five examined runs have byte-identical actor configuration headers,
  including feedback mapping, gains, limits, startup parameters, and action
  scaling. The deployed policy and original CAN controller hashes are unchanged.
- Each SPI run's 6001 consumed-input records reproduce its entire recorded actor
  output byte-for-byte in **both** the original offline executable and the new
  candidate offline executable. This covers observations, history, inference,
  targets, and protected outputs for those inputs, not closed-loop equivalence.
- Every consumed SPI gyro/gravity pair matches a saved producer sample at full
  precision. No sequence regression or repeated sample at successive policy
  ticks was found. Sensor data is not blended with OpenIMU.
- SPI integration still uses actual GPIO DRDY timestamp differences. The client
  request period is not the estimator integration timestep, policy timestep, or
  history advancement rate. Ordinary motors remain 50 Hz; ankles remain 500 Hz.
- The new raw capture's 13.893646 ms maximum gap occurred approximately 1.642 s
  **before** the powered policy interval. It does not coincide with small-step
  walking. Both runs also contain an approximately 42 ms initial policy-state
  interval; subsequent states remain at approximately 20 ms. That startup
  feature is not new to this candidate.

### Conclusion and next controlled comparison

The reported gait change is supported by joint feedback. It already appears in
the actor targets, not solely as a failure to track identical targets. No rate
scaling, stale-data, gain/configuration, or deterministic inference mismatch was
found in these records. The physical cause is **not established**.

Snapshot freshness changes IMU-versus-joint timing and the sampled gyro history
in a closed loop. This is a hypothesis to test, not proof that lower latency
causes the regression. Starting posture, harness loading, ground contact, and
other trial conditions were not controlled by these logs.

The next powered experiment, with fresh onsite approval, should compare the
unchanged original SPI entry against this candidate with the same stationary
calibration, initial pose, support, battery, and a sustained straight 0.10 m/s
command. Prefer A-B-A repetition over changing PD or adding filters. Sensor ODR
stays 800 Hz in both cases; only the snapshot client differs. Until then the
original stable entry remains the recommended baseline. No rollback file or
powered entry was modified by this investigation.

## Successful SPI compatibility follow-up

On 2026-11-24 the user corrected a right-ankle linkage/encoder-turn situation and
power-cycled the robot. Earlier preflights at 18:10:54 and 18:12:59 rejected the
converted ankle pose before actuation. No zero-reset command or relaxed angle
limit was used by this update. These preflight failures are not walking trials.

The subsequent original-client A1 run, `20261124_181742`, was described as working
by the operator, but its controller report is `passed: false`: 5,218 targets were
received before `policy IPC client disconnected` (approximately 104 seconds of
50 Hz targets). All 31 motors were subsequently verified disabled. The recorded
reason does not establish whether this was an intentional interruption; do not
label it a completed 120-second pass or a fully controlled A-B-A comparison.

The new SPI snapshot-client B run, `20261124_182201`, completed normally:

| Evidence | Result |
| --- | --- |
| Native actor | exit 0, passed |
| Native controller | passed, no errors |
| Schedule | 120 seconds |
| Policy states / targets | 6,001 / 6,000 |
| Scheduler deadline misses | 0 |
| Maximum scheduling lateness | 0.037876 ms |
| Final motor status | all 31 verified disabled |
| Operator feedback | walking normal; no observed oscillation in this SPI compatibility trial |

Source reports are `native_protected_policy_actor_imu800_20261124_182201.json`
and `native_protected_policy_admission_imu800_20261124_182201.json` in the baseline
deployment's `reports` directory. Compact public evidence, including source
hashes, is in [the release summary](evidence/IMU800_SPI_20261124.json). Raw motor
traces and machine-specific sealed candidate binaries are not bundled here.

The SPI compatibility test command is:

```bash
cd /home/tony/open_sprite_runtime_openimu
sudo bash run_sprite0825_xbox_imu800_turn120_on_253.sh ENABLE_XBOX_TURN120 --imu icm-spi
```

For this compatibility test, `--imu icm-spi` is essential: the wrapper defaults to OpenIMU
when omitted. Both producers remain mutually exclusive. The original entry
still uses its original 200 Hz snapshot-client actor; no default selector was
silently redirected. Existing offline preparation receipts keep their original
`powered_test_completed: false` status because they describe preparation, not
this later physical test. The release summary records the subsequent result.

For the primary OpenIMU runtime, use the same `imu800` wrapper without
`--imu icm-spi` (or with `--imu openimu`). The SPI test result does not change that
recommendation, and its subjective no-oscillation observation is not transferred
to OpenIMU.

## Provisioning boundaries

The repository supplies source and preparation/qualification tools, not a
portable, automatically armable deployment. The existing baseline includes
site-specific motor maps, linkage calibration, policy/contract, source copies,
ONNX Runtime library, joystick mapping, and sealed fake-peer evidence.

The preparation sequence on that already provisioned machine is:

1. `tools/qualify_imu_client800.py`: build an isolated actor and run synthetic
   peer parity/fault tests. The deployment tooling expects the reviewed build
   under `candidates/imu_client800_20261124_v2`.
2. `tools/prepare_imu_client800_shadow.py`: create and validate the zero-gain
   candidate, without starting hardware.
3. `qualify_sprite0825_imu800_shadow_on_253.sh`: explicit, supported, disabled-motor
   real-feedback tests for each backend separately.
4. `tools/prepare_imu_client800_entry.py`: verify the reviewed source/seal and
   zero-gain evidence, copy parameters, and generate separate powered entries.

The current entry preparer deliberately pins the recorded qualification report
directories from this commissioning session. A fresh installation needs its own
reviewed evidence and matching seals; it must not fabricate those reports or
bypass missing-evidence checks. The preparer refuses to overwrite an existing
candidate. On this robot the sealed package is already installed; do not rebuild
or overwrite it merely to update documentation from GitHub.
