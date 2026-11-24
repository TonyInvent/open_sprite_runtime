"""Select an IMU around the sealed mixed-rate Xbox runtime, without changing it."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

from openimu_interface import find_openimu, link, require_active

ROOT = Path(__file__).resolve().parents[1]
ACK = "ENABLE_XBOX_TURN120"
SPI_ENTRY = "run_sprite0825_xbox_native_turn120_on_253.sh"
INNER = "run_sprite0825_xbox_native_turn120_inner.sh"
CANDIDATE = "candidates/xbox_native_turn120_20261019"


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=[ACK], nargs="?")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", dest="check", action="store_true", help="offline seals only; no hardware access")
    mode.add_argument("--imu-only", action="store_true", help="receive IMU and validate IPC; no motor CAN access")
    mode.add_argument("--preflight-only", action="store_true", help="existing zero-gain motor preflight; no enable")
    parser.add_argument("--imu", choices=["openimu", "icm-spi"], default="openimu")
    parser.add_argument("--imu-can-interface", help="dedicated PCAN-USB FD, auto-discovered if omitted")
    parser.add_argument("--duration", type=int, default=60, help="IMU-only seconds after calibration, 1..560")
    parser.add_argument("--view", action="store_true", help="MuJoCo attitude display with --imu-only; no motor access")
    parser.add_argument("--baseline-root", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    args = parser.parse_args(argv)
    selected = [name for name, enabled in [("--check", args.check), ("--imu-only", args.imu_only),
                                          ("--preflight-only", args.preflight_only)] if enabled]
    if args.action:
        selected.append(args.action)
    if len(selected) != 1:
        parser.error("select exactly one of --check, --imu-only, --preflight-only, or " + ACK)
    args.action = selected[0]
    if not 1 <= args.duration <= 560:
        parser.error("--duration must be 1..560")
    if args.imu == "icm-spi" and (args.imu_can_interface or args.action == "--imu-only"):
        parser.error("SPI fallback supports --check, --preflight-only, or the existing powered acknowledgement")
    if args.duration != 60 and args.action != "--imu-only":
        parser.error("--duration only applies to --imu-only; walking remains the sealed 120s")
    if args.view and (args.action != "--imu-only" or args.imu != "openimu"):
        parser.error("--view requires --imu-only with OpenIMU")
    return args


def legacy_command(args):
    return ["bash", str(args.baseline_root / SPI_ENTRY), args.action]


def check_baseline(root):
    subprocess.run(["bash", str(root / INNER), "--check"], cwd=root, check=True)


def no_running_runtime(proc=Path("/proc")):
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            name = (entry / "exe").resolve(strict=True).name
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if name.startswith(("sprite_can_", "sprite_policy_", "sprite_imu_", "sprite_icm45686", "sprite_openimu")):
            raise RuntimeError("Stop the existing runtime/IMU process first: " + name)


def stop_group(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        # The controller's own target-age watchdog still applies. Never silently
        # claim a powered shutdown succeeded after killing an unresponsive tree.
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise RuntimeError("Child shutdown timed out; inspect motor disable verification")


def read_latest(endpoint, local, duration):
    from open_sprite_runtime.native_imu_packet import decode_icm_packet

    started = time.monotonic()
    last_sequence = 0
    count = repeated = 0
    maximum_age_ms = 0.0
    accel_sum = [0.0] * 3
    gyro_sum = [0.0] * 3
    gravity_sum = [0.0] * 3
    maximum_gyro = 0.0
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.bind(str(local))
        client.settimeout(.1)
        while time.monotonic() - started < duration:
            client.sendto(b"GETIMU01", str(endpoint))
            packet = client.recv(193)
            decode_icm_packet(packet, now_ns=time.monotonic_ns(), previous_sequence=last_sequence)
            # Decoder performs the existing icm-v3 scale, norm and freshness checks.
            sequence, sampled, _ = struct.unpack_from("<QQQ", packet, 8)
            if sequence < last_sequence:
                raise RuntimeError("IMU sequence regressed")
            repeated += int(sequence == last_sequence)
            last_sequence = sequence
            maximum_age_ms = max(maximum_age_ms, (time.monotonic_ns() - sampled) / 1e6)
            values = struct.unpack_from("<13d", packet, 80)
            body_a = [-values[2], -values[1], -values[0]]
            body_w = [-values[5], -values[4], -values[3]]
            gravity = [values[12] / 9.80665, values[11] / 9.80665, values[10] / 9.80665]
            for i in range(3):
                accel_sum[i] += body_a[i]
                gyro_sum[i] += body_w[i]
                gravity_sum[i] += gravity[i]
            maximum_gyro = max(maximum_gyro, math.sqrt(sum(v*v for v in body_w)))
            count += 1
            time.sleep(.02)
    return dict(samples=count, repeated_sequences=repeated, maximum_age_ms=maximum_age_ms,
                mean_body_accel_m_s2=[v/count for v in accel_sum],
                mean_body_gyro_rad_s=[v/count for v in gyro_sum], maximum_gyro_rad_s=maximum_gyro,
                mean_projected_gravity=[v/count for v in gravity_sum])


def session(args):
    baseline = args.baseline_root.resolve(strict=True)
    producer = ROOT / "build/openimu/sprite_openimu"
    if args.action != "--imu-only":
        check_baseline(baseline)
    subprocess.run([str(producer), "--help"], check=True)
    if args.action == "--check":
        print("MIXED_RATE_OPENIMU_CHECK_OK: existing actor, gains and CAN binary unchanged; no hardware access")
        return 0
    viewer_cmd = ["python3", str(ROOT / "tools/view_openimu.py"),
                  "--baseline-root", str(baseline)]
    if args.view:
        subprocess.run([*viewer_cmd, "--check"], check=True)
    adapter = find_openimu(args.imu_can_interface)
    require_active(link(adapter["interface"]))
    no_running_runtime()
    report_root = ROOT / "reports"
    report_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="xbox_openimu_", dir=report_root))
    report = dict(imu="openimu", adapter=adapter, action=args.action, passed=False,
                  policy_hz=50, ordinary_motor_hz=50, ankle_motor_hz=500,
                  imu_nominal_hz=800, errors=[])
    print("REPORT_DIRECTORY", out, flush=True)
    print("Keep stationary for 15s. OpenIMU receive-only calibration; motor CAN has not started.", flush=True)
    with tempfile.TemporaryDirectory(prefix="sprite_openimu_") as folder, (out / "imu.log").open("w") as imu_log:
        endpoint = Path(folder) / "imu.sock"
        env = dict(os.environ, ICM_IPC_SOCKET=str(endpoint), SPRITE_NATIVE_IMU_SOCKET=str(endpoint),
                   SPRITE_NATIVE_IMU_PROTOCOL="icm-v3",
                   SPRITE_PREFLIGHT_ONLY="1" if args.action == "--preflight-only" else "0")
        capture_seconds = args.duration + 30 if args.action == "--imu-only" else 300
        process = walk = viewer = None
        try:
            process = subprocess.Popen([str(producer), "capture-canfd", adapter["interface"],
                                        str(capture_seconds), str(out / "imu.csv")],
                                       env=env, stdout=imu_log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 25
            while "BIAS_READY" not in (out / "imu.log").read_text():
                if process.poll() is not None:
                    raise RuntimeError("OpenIMU exited during calibration; see imu.log")
                if time.monotonic() >= deadline:
                    raise RuntimeError("OpenIMU stationary calibration timed out")
                time.sleep(.1)
            report["ipc_check"] = read_latest(endpoint, Path(folder) / "check.sock",
                                              args.duration if args.action == "--imu-only" and not args.view else .25)
            if args.action == "--imu-only":
                if args.view:
                    viewer_report = out / "viewer.json"
                    with (out / "viewer.log").open("w") as log:
                        viewer = subprocess.Popen([*viewer_cmd, "--socket", str(endpoint),
                                                   "--duration", str(args.duration), "--report", str(viewer_report)],
                                                  env=env, stdout=log, stderr=subprocess.STDOUT,
                                                  start_new_session=True)
                        with (out / "viewer.log").open() as reader:
                            deadline = time.monotonic() + args.duration + 10
                            while viewer.poll() is None:
                                print(reader.read(), end="", flush=True)
                                if process.poll() is not None:
                                    raise RuntimeError("OpenIMU exited; closing display")
                                if time.monotonic() >= deadline:
                                    raise RuntimeError("IMU viewer exceeded bounded time")
                                time.sleep(.1)
                            print(reader.read(), end="", flush=True)
                    report["viewer_exit"] = viewer.returncode
                    if viewer_report.exists():
                        report["viewer"] = json.loads(viewer_report.read_text())
                    if viewer.returncode != 0:
                        raise RuntimeError("IMU viewer failed; see viewer.log")
                report["passed"] = process.poll() is None
                if not report["passed"]:
                    raise RuntimeError("OpenIMU exited during receive-only validation")
            else:
                print("IMU_READY: starting unchanged mixed-rate Xbox admission. See baseline reports for CAN/actor results.", flush=True)
                with (out / "admission.log").open("w") as log:
                    walk = subprocess.Popen(["bash", str(baseline / CANDIDATE / "admission.sh"), ACK],
                                            cwd=baseline, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            start_new_session=True)
                    # Tail outside the real-time processes; IMU and CAN never wait for this terminal.
                    with (out / "admission.log").open() as reader:
                        deadline = time.monotonic() + 240
                        while walk.poll() is None:
                            print(reader.read(), end="", flush=True)
                            if process.poll() is not None:
                                raise RuntimeError("OpenIMU exited; stopping admission")
                            if time.monotonic() >= deadline:
                                raise RuntimeError("Admission exceeded its bounded session time")
                            time.sleep(.1)
                        print(reader.read(), end="", flush=True)
                    report["admission_exit"] = walk.returncode
                    if walk.returncode != 0:
                        raise RuntimeError("Mixed-rate admission failed; see admission.log")
                    report["passed"] = True
        except BaseException as exc:
            report["errors"].append(str(exc) or type(exc).__name__)
            report["passed"] = False
        finally:
            report["producer_stopped_by_launcher"] = process is not None and process.poll() is None
            for child in (walk, viewer, process):
                try:
                    stop_group(child)
                except Exception as exc:
                    report["errors"].append(str(exc))
                    report["passed"] = False
            report["producer_exit"] = None if process is None else process.returncode
            (out / "session.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


def main():
    args = arguments()
    if args.imu == "icm-spi":
        # This is the original script, not a reimplementation of SPI or walking.
        os.execvp("bash", legacy_command(args))
    if os.geteuid() == 0:
        if os.environ.get("SUDO_USER") != "tony":
            raise SystemExit("Run as tony (sudo from tony is also accepted)")
        os.execvp("runuser", ["runuser", "-u", "tony", "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    baseline_python = args.baseline_root / "candidates/icm_native_20261016/python"
    sys.path.insert(0, str(baseline_python))
    # Prevent concurrent launches through this selector. Existing native processes
    # are also refused; the old stable scripts remain byte-for-byte unchanged.
    with (ROOT / ".openimu-session.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def interrupted(*_):
            raise KeyboardInterrupt("Session interrupted; shutting down children")

        signal.signal(signal.SIGTERM, interrupted)
        raise SystemExit(session(args))


if __name__ == "__main__":
    main()
