# Script directory guide

## Current workflow

OpenIMU CAN FD at nominal 800 Hz is the primary backend. Start with the
[main README](../README.md), not with an arbitrary commissioning script.

| Task | Entry retained at repository root |
| --- | --- |
| Recommended Xbox walking entry; OpenIMU by default | [run_sprite0825_xbox_imu800_turn120_on_253.sh](../run_sprite0825_xbox_imu800_turn120_on_253.sh) |
| Offline integrity checks | The same entry with `--check` |
| SPI compatibility comparison | The same entry with explicit `--imu icm-spi` and the documented acknowledgement |
| OpenIMU attitude viewer; no motor commands | [review_sprite0825_openimu_mujoco_on_253.sh](../review_sprite0825_openimu_mujoco_on_253.sh) |
| Separate OpenIMU/SPI zero-gain qualification | [qualify_sprite0825_imu800_shadow_on_253.sh](../qualify_sprite0825_imu800_shadow_on_253.sh) |
| OpenIMU native build | [build_sprite0825_openimu_on_253.sh](../build_sprite0825_openimu_on_253.sh) |
| Configure the four motor CAN FD buses | [setup_sprite0825_kcanfd_on_253.sh](../setup_sprite0825_kcanfd_on_253.sh) |

The dedicated OpenIMU interface `spriteimu0` has separate configuration:
see [OpenIMU commissioning](../docs/OPENIMU_MIXED_RATE_XBOX.md).
The scripts remain site-specific and require the matched deployment package,
calibration, reviewed parameter bundle, and existing integrity evidence.
An entry being retained is not permission to run it on hardware.

## Cleanup scope

On November 24, 2026, the root was reduced from **96 to 32 Shell scripts**.
The other **64 scripts were moved without changing their contents**:

- `archive/motor_commissioning/`: individual joints, differential mechanisms,
  register inspection, zero-gain bus probes, and earlier commissioning operations.
- `archive/imu_diagnostics/`: historical sensor, SPI wiring/clock, and attitude tests.
- `archive/legacy_trials/`: earlier policy admission, timing, and shadow experiments.
- `archive/system_identification/`: historical capture and merge entry points.

These are historical references, not newly qualified commands. Some enable
motors, change configuration, or reset motor zero positions. **Do not run them
merely because they are in this archive.** No motor-zero operation is part of
this cleanup.

The [inventory](inventory_20261124.json) records every original root filename,
its current location, its retention reason, and its pre-cleanup SHA-256
(LF-normalized, matching the repository's Shell line-ending convention).
No script was discarded. No controller, sensor processing, gains, limits,
acknowledgements, or sealed candidate files were changed. Nothing was deployed
to the Jetson.

## Why 32 scripts remain

The OpenIMU selector still checks the provisioned stable Xbox baseline. Historical
candidate builders and seals also refer to older entry filenames. Moving these
files would require a separate compatibility migration and renewed validation,
so their paths and contents remain intact. The list below distinguishes current
entries from those dependency files; their presence does not make BNO or SPI
the primary backend.

| Retained root file | Role |
| --- | --- |
| [build_sprite0825_icm45686_on_253.sh](../build_sprite0825_icm45686_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [build_sprite0825_native_runtime_on_253.sh](../build_sprite0825_native_runtime_on_253.sh) | Build, installation, or CLI support |
| [build_sprite0825_openimu_on_253.sh](../build_sprite0825_openimu_on_253.sh) | Current OpenIMU workflow |
| [compare_sprite0825_openimu_spi_on_253.sh](../compare_sprite0825_openimu_spi_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [install_sprite0825_imu_udev_on_253.sh](../install_sprite0825_imu_udev_on_253.sh) | Build, installation, or CLI support |
| [install_sprite0825_native_realtime_capability_on_253.sh](../install_sprite0825_native_realtime_capability_on_253.sh) | Build, installation, or CLI support |
| [install_sprite0825_native_runtime_capabilities_on_253.sh](../install_sprite0825_native_runtime_capabilities_on_253.sh) | Build, installation, or CLI support |
| [probe_sprite0825_bno055_policy_shadow_on_253.sh](../probe_sprite0825_bno055_policy_shadow_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [probe_sprite0825_icm45686_on_253.sh](../probe_sprite0825_icm45686_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [qualify_sprite0825_imu800_shadow_on_253.sh](../qualify_sprite0825_imu800_shadow_on_253.sh) | Current OpenIMU workflow |
| [review_sprite0825_openimu_mujoco_on_253.sh](../review_sprite0825_openimu_mujoco_on_253.sh) | Current OpenIMU workflow |
| [run_sprite_runtime_jetson.sh](../run_sprite_runtime_jetson.sh) | Build, installation, or CLI support |
| [run_sprite0825_bno055_waist60kd3_walk40_on_253.sh](../run_sprite0825_bno055_waist60kd3_walk40_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_full_native_walk40_candidate_on_253.sh](../run_sprite0825_full_native_walk40_candidate_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_icm_native_admission.sh](../run_sprite0825_icm_native_admission.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_icm_native_walk40_inner.sh](../run_sprite0825_icm_native_walk40_inner.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_icm_native_walk40_on_253.sh](../run_sprite0825_icm_native_walk40_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_native_actor_admission_candidate.sh](../run_sprite0825_native_actor_admission_candidate.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_software_imu_walk40_on_253.sh](../run_sprite0825_software_imu_walk40_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_upper_body_pd_native_admission.sh](../run_sprite0825_upper_body_pd_native_admission.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_upper_body_pd_native_walk40_on_253.sh](../run_sprite0825_upper_body_pd_native_walk40_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_imu_turn120_on_253.sh](../run_sprite0825_xbox_imu_turn120_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [run_sprite0825_xbox_imu800_turn120_on_253.sh](../run_sprite0825_xbox_imu800_turn120_on_253.sh) | Current OpenIMU workflow |
| [run_sprite0825_xbox_native_admission.sh](../run_sprite0825_xbox_native_admission.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_native_forward120_inner.sh](../run_sprite0825_xbox_native_forward120_inner.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_native_forward120_on_253.sh](../run_sprite0825_xbox_native_forward120_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_native_forward40_inner.sh](../run_sprite0825_xbox_native_forward40_inner.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_native_forward40_on_253.sh](../run_sprite0825_xbox_native_forward40_on_253.sh) | Historical dependency retained for candidate generation or integrity checks; not a recommended entry |
| [run_sprite0825_xbox_native_turn120_inner.sh](../run_sprite0825_xbox_native_turn120_inner.sh) | Compatibility or comparison; not the primary walking entry |
| [run_sprite0825_xbox_native_turn120_on_253.sh](../run_sprite0825_xbox_native_turn120_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [setup_sprite_spi_low_clock_on_253.sh](../setup_sprite_spi_low_clock_on_253.sh) | Compatibility or comparison; not the primary walking entry |
| [setup_sprite0825_kcanfd_on_253.sh](../setup_sprite0825_kcanfd_on_253.sh) | Current OpenIMU workflow |

## Reading historical instructions

Earlier development documents intentionally retain their original command lines
and site paths as evidence. If a named root script is now absent, locate it in
the inventory or in `scripts/archive/`; do not substitute an unrelated script.

Archived scripts are **not relocation-ready runnable tools**. They retain their
original root-relative paths and, in some cases, absolute deployment paths.
Their helper code, reports, and calibration also belong to their original
deployment. For source inspection and historical reproduction, create a separate
checkout of the last complete pre-cleanup layout:

```bash
git worktree add --detach ../open_sprite_runtime_pre_cleanup 76f199ec74d1014dd840bf34026c5662063fb9f4
```

This command only creates a source checkout. It does not install calibrated
assets, binaries, evidence, or hardware permissions, and does not qualify an old
test for today's robot. Do not copy archived scripts over the working deployment
or bypass a seal to make an old test run. Historical helpers under `tools/`
remain available; the old checkout supplies their original companion scripts.

## Maintenance checks

```bash
python3 -m unittest discover -s tests -p 'test_script_layout.py'
```

This offline check validates the inventory, archive hashes, retained paths, and
references from retained Shell scripts and repository code. It opens no sensor
or motor interface. No new root-level compatibility stubs were added.
