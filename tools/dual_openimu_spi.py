"""Guided dual-IMU capture. OpenIMU RX + SPI sensor configuration; no motor access."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from openimu_interface import find_openimu, link, require_active
from xbox_imu_session import ROOT, no_running_runtime, stop_group

PHASES = [
    ("still", 5, "KEEP STILL; hands off if mechanically supported."),
    ("pitch", 12, "Slowly lean FORWARD, then BACKWARD, then return to start. Do not twist."),
    ("rest_pitch", 5, "RETURN to start and KEEP STILL."),
    ("roll", 12, "Slowly lean LEFT, then RIGHT, then return to start. Do not twist."),
    ("rest_roll", 5, "RETURN to start and KEEP STILL."),
    ("yaw", 12, "Slowly TURN LEFT, then RIGHT, then return to start. Keep upright."),
    ("final_still", 5, "RETURN to start and KEEP STILL."),
]


def producer_commands(spi, can, interface, chip, offset, out):
    return {
        "openimu": [str(can), "capture-canfd", interface, "180", str(out / "openimu.csv")],
        "spi": [str(spi), "capture", "/dev/spidev0.0", "/dev/"+chip, offset, "800", "180",
                str(out / "spi.csv"), "X_DOWN_Z_BACK", "CONFIGURE_ICM45686_RAW_NO_CAN"],
    }


def capture(args):
    baseline = args.baseline_root
    spi = baseline / "candidates/icm_native_20261016/build/sprite_icm45686"
    can = ROOT / "build/openimu/sprite_openimu"
    for binary in (spi, can):
        if not os.access(binary, os.X_OK):
            raise RuntimeError("Missing prepared producer: " + str(binary))
    adapter = find_openimu(args.imu_can_interface)
    require_active(link(adapter["interface"]))
    no_running_runtime()
    if Path("/sys/bus/platform/devices/3210000.spi/power/control").read_text().strip() != "on":
        raise RuntimeError("Run the scoped SPI PM wrapper")
    chip, offset = subprocess.check_output(["gpiofind", "PY.01"], text=True).split()
    print("NO MOTOR CAN TX / NO POLICY / NO ENABLE.", flush=True)
    print("Both IMUs must be rigidly mounted to the same body, sensor X down and Z back.", flush=True)
    print("Support the robot; use small, slow motions. Do not move during calibration.", flush=True)
    input("Press ENTER when stationary and ready for 15s calibration: ")
    (ROOT / "reports").mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="dual_openimu_spi_", dir=ROOT / "reports"))
    report = dict(mode="guided_dual_imu_no_motor_access", adapter=adapter, phases=[], errors=[],
                  acquisition_completed=False, direction_verified=False, no_motor_can_tx=True,
                  spi_configuration_writes=True)
    print("REPORT_DIRECTORY", out, flush=True)
    commands = producer_commands(spi, can, adapter["interface"], chip, offset, out)
    children, logs = {}, {}
    try:
        # No IPC clients are needed: both producers retain native-rate raw data.
        env = dict(os.environ)
        env.pop("ICM_IPC_SOCKET", None)
        env.pop("ICM_VIEW_STDOUT", None)
        for name, command in commands.items():
            logs[name] = (out / (name+".log")).open("w")
            children[name] = subprocess.Popen(command, env=env, stdout=logs[name],
                                              stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic()+25
        print("CALIBRATING: KEEP STILL until BOTH_READY.", flush=True)
        while True:
            for name, child in children.items():
                if child.poll() is not None:
                    raise RuntimeError(name+" exited during calibration; see its log")
            if all("BIAS_READY" in (out / (name+".log")).read_text() for name in children):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Dual stationary calibration timed out")
            time.sleep(.1)
        print("BOTH_READY: follow the timed prompts below.\a", flush=True)
        for name, duration, prompt in PHASES:
            phase = dict(name=name, duration_s=duration, start_ns=time.monotonic_ns(), prompt=prompt)
            report["phases"].append(phase)
            print(f"\nPHASE {name.upper()} ({duration}s): {prompt}\a", flush=True)
            end = time.monotonic()+duration
            last_remaining = None
            while time.monotonic() < end:
                for source, child in children.items():
                    if child.poll() is not None:
                        raise RuntimeError(source+" exited during "+name)
                remaining = max(0, int(end-time.monotonic())+1)
                if remaining != last_remaining:
                    print(f"  {name}: {remaining}s remaining", flush=True)
                    last_remaining = remaining
                time.sleep(.1)
            phase["end_ns"] = time.monotonic_ns()
        report["acquisition_completed"] = True
        print("DONE: acquisition is stopping. No motors were enabled.", flush=True)
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
    finally:
        report["launcher_requested_stop"] = {name: p.poll() is None for name, p in children.items()}
        for name, child in children.items():
            try:
                stop_group(child)
            except Exception as exc:
                report["errors"].append(name+": "+str(exc))
        for log in logs.values():
            log.close()
        report["producer_exit"] = {name: p.returncode for name, p in children.items()}
        report["acquisition_completed"] &= not report["errors"]
        (out / "session.json").write_text(json.dumps(report, indent=2)+"\n")
        print("REPORT_DIRECTORY", out, flush=True)
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report["acquisition_completed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    parser.add_argument("--imu-can-interface")
    args = parser.parse_args()
    def interrupt(*_):
        raise KeyboardInterrupt("Capture interrupted")
    signal.signal(signal.SIGTERM, interrupt)
    with (ROOT / ".openimu-session.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raise SystemExit(capture(args))


if __name__ == "__main__":
    main()
