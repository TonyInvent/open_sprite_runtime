#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
echo 'OPENIMU RECEIVE ONLY: no motor CAN frames, no enable, no policy.'
echo 'Keep still for 15s; move only after VIEW_READY. Display duration excludes calibration.'
exec bash ./run_sprite0825_xbox_imu_turn120_on_253.sh --imu-only --view --duration "${1:-120}"
