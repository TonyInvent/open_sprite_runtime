"""Bind the dedicated PCAN USB port to spriteimu0; never configure motor buses."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from openimu_interface import find_openimu, link, require_active

NAME = "spriteimu0"
RULE = Path("/etc/udev/rules.d/90-sprite-openimu-net.rules")


def naming_rule(adapter):
    port = adapter["usb_port"]
    if not re.fullmatch(r"[0-9]+-[0-9]+(?:\.[0-9]+)*", port):
        raise ValueError("Invalid USB topology identifier")
    return ('# Dedicated OpenIMU adapter, bound to this physical USB port.\n'
            'ACTION=="add", SUBSYSTEM=="net", ATTR{type}=="280", '
            'ATTRS{idVendor}=="0c72", ATTRS{idProduct}=="0012", '
            f'KERNELS=="{port}", NAME:="{NAME}"\n')


def validate_target(adapter, state, target_exists):
    if adapter["interface"] != NAME:
        if target_exists:
            raise RuntimeError("spriteimu0 already exists; refuse name collision")
        if "UP" in state["flags"]:
            raise RuntimeError("Stop IMU users and bring only the dedicated IMU link DOWN before renaming")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="install naming rule and bring up IMU only")
    args = parser.parse_args()
    adapter = find_openimu()
    old = adapter["interface"]
    state = link(old)
    validate_target(adapter, state, Path("/sys/class/net", NAME).exists())
    content = naming_rule(adapter)
    if RULE.is_symlink() or (RULE.exists() and RULE.read_text() != content):
        raise RuntimeError("Existing naming rule differs; review it before changing USB-port binding")
    print(json.dumps(dict(adapter=adapter, target=NAME, rule=str(RULE), apply=args.apply)))
    print(content, end="")
    if not args.apply:
        return
    if os.geteuid() != 0:
        raise RuntimeError("Installation requires sudo")
    if int(subprocess.check_output(["udevadm", "--version"]).strip()) < 247:
        raise RuntimeError("Final name assignment requires udev >=247")
    if "UP" in state["flags"]:
        require_active(state)
    RULE.write_text(content, encoding="ascii")
    RULE.chmod(0o644)
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    if old != NAME:
        # Trigger only this already-DOWN adapter, never the motor links.
        subprocess.run(["udevadm", "trigger", "--action=add", f"/sys/class/net/{old}"], check=True)
        subprocess.run(["udevadm", "settle", "--timeout=10"], check=True)
    selected = find_openimu(NAME)
    if selected["usb_port"] != adapter["usb_port"]:
        raise RuntimeError("USB identity changed during installation")
    state = link(NAME)
    if "UP" not in state["flags"]:
        subprocess.run(["ip", "link", "set", "dev", NAME, "type", "can", "bitrate", "1000000",
                        "dbitrate", "5000000", "fd", "on"], check=True)
        subprocess.run(["ip", "link", "set", "dev", NAME, "up"], check=True)
    require_active(link(NAME))
    print("OPENIMU_NAME_OK interface=spriteimu0 bitrate=1000000 dbitrate=5000000 NO_MOTOR_COMMANDS")
    print("Persistent name installed. Link UP remains an explicit setup step after reboot.")


if __name__ == "__main__":
    main()
