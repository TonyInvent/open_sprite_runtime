#!/usr/bin/env bash
set -euo pipefail
[[ "$EUID" == 0 && "${SUDO_USER:-}" == tony ]] || { echo 'Run with sudo as tony'; exit 2; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec 9>/run/lock/sprite_icm_spi_pm.lock
flock -n 9 || { echo 'Another SPI test/runtime holds the PM lock'; exit 2; }
pm=/sys/bus/platform/devices/3210000.spi/power/control
old=$(<"$pm")
[[ "$old" == auto || "$old" == on ]] || { echo 'Unexpected SPI PM state'; exit 2; }
restore() { printf '%s\n' "$old" > "$pm"; echo "RESTORED SPI PM=$old"; }
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'on\n' > "$pm"
runuser -u tony -- /home/tony/open_sprite_runtime/.venv/bin/python "$PWD/tools/dual_openimu_spi.py" "$@"
