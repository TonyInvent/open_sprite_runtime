#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
cmake -S native/icm45686 -B build/openimu -DCMAKE_BUILD_TYPE=Release
cmake --build build/openimu --target sprite_openimu openimu_test icm_offline_test icm_packet_test -j2
ctest --test-dir build/openimu --output-on-failure
echo 'OpenIMU receiver built and offline tests passed. No CAN/SPI access or motor commands.'
