#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The final option pins this entry to the qualified 800 Hz snapshot client.
exec /home/tony/open_sprite_runtime/.venv/bin/python "$ROOT/tools/xbox_imu_session.py" "$@" --snapshot-client-hz 800
