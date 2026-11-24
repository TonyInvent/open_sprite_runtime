#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /home/tony/open_sprite_runtime/.venv/bin/python "$ROOT/tools/xbox_imu_session.py" "$@"
