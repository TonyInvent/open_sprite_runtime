"""Locate the dedicated PCAN-USB FD and bring up the OpenIMU link on request.

Adapted from TonyInvent/MacMimic bc7be0a (AGPL-3.0).
The motor buses kcan1..4 must never be selected or reconfigured here.
"""
import argparse
import json
from pathlib import Path
import subprocess


def find_openimu(interface=None, net=Path("/sys/class/net")):
    if interface in {"kcan1", "kcan2", "kcan3", "kcan4"}:
        raise ValueError("OpenIMU requires a dedicated adapter, never a motor bus")
    matches = []
    for entry in net.iterdir():
        if entry.name in {"kcan1", "kcan2", "kcan3", "kcan4"}:
            continue
        if interface and entry.name != interface:
            continue
        if not (entry / "type").exists() or (entry / "type").read_text().strip() != "280":  # ARPHRD_CAN
            continue
        for usb in (entry / "device").resolve().parents:
            if (usb / "idVendor").exists():
                usb_id = tuple((usb / field).read_text().strip() for field in ("idVendor", "idProduct"))
                if usb_id == ("0c72", "0012"):
                    serial = usb / "serial"
                    matches.append(dict(backend="canfd", interface=entry.name, usb_port=usb.name,
                                        serial=serial.read_text().strip() if serial.exists() else ""))
                break
    if len(matches) != 1:
        raise ValueError("Expected one PCAN-USB FD OpenIMU interface; check USB or select --imu-can-interface")
    return matches[0]


def link(name):
    return json.loads(subprocess.check_output(["ip", "-j", "-d", "link", "show", "dev", name]))[0]


def require_active(state):
    data = state.get("linkinfo", {}).get("info_data", {})
    if ("UP" not in state.get("flags", []) or state.get("mtu") != 72 or
            data.get("bittiming", {}).get("bitrate") != 1000000 or
            data.get("data_bittiming", {}).get("bitrate") != 5000000 or
            data.get("state") in {"BUS-OFF", "STOPPED", "SLEEPING"}):
        raise ValueError("OpenIMU requires UP, CAN FD MTU72, 1M/5M, non-BUS-OFF; run setup explicitly")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imu-can-interface")
    parser.add_argument("--up", action="store_true", help="configure a stopped adapter for 1 Mbit/s / 5 Mbit/s FD")
    parser.add_argument("--check", action="store_true", help="require an active link without changing it")
    args = parser.parse_args()
    adapter = find_openimu(args.imu_can_interface)
    name = adapter["interface"]
    state = link(name)
    if args.up and "UP" not in state["flags"]:
        subprocess.run(["ip", "link", "set", "dev", name, "type", "can", "bitrate", "1000000",
                        "dbitrate", "5000000", "fd", "on"], check=True)
        subprocess.run(["ip", "link", "set", "dev", name, "up"], check=True)
        state = link(name)
    data = state["linkinfo"]["info_data"]
    print(json.dumps(dict(adapter=adapter, flags=state["flags"], mtu=state["mtu"], can=data)))
    if args.up or args.check:
        require_active(state)


if __name__ == "__main__":
    main()
