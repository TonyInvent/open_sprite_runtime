"""Exclusive-backend 800 Hz snapshot qualification; zero-gain motor queries only."""
import argparse
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np
from openimu_interface import find_openimu, link, require_active
from xbox_imu_session import no_running_runtime

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("/home/tony/open_sprite_runtime")
CLIENT = ROOT / "candidates/imu_client800_20261124_v2"
SHADOW = ROOT / "candidates/imu_client800_shadow_20261124"
UPPER = BASE / "candidates/upper_body_pd_wrist7_20261014"
ACK = "ZERO_GAIN_IMU800_ALL_DISABLED_SUPPORTED"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    qualification = json.loads((SHADOW / "qualification.json").read_text())
    if qualification.get("passed") is not True:
        raise RuntimeError("Shadow actor offline qualification missing")
    for name, sha in qualification["sha256"].items():
        if digest(Path(name)) != sha:
            raise RuntimeError("Qualified input changed: " + name)
    subprocess.run([sys.executable, str(BASE / "candidates/xbox_native_turn120_20261019/check_powered_seal.py")], check=True)
    contract = json.loads((UPPER / "deploy/contract.json").read_text())
    with (UPPER / "motors.tsv").open() as file:
        motors = list(csv.DictReader(file, delimiter="\t"))
    if len(motors) != 31 or len(contract["joint_names"]) != 31:
        raise RuntimeError("Require exactly 31 motors/joints")
    fast = {m["motor_name"] for m in motors if int(m["poll_rate_hz"]) == 500}
    expected = {f"{side}_ankle_motor_{part}" for side in ("left", "right") for part in ("a", "b")}
    if fast != expected or any(int(m["poll_rate_hz"]) != (500 if m["motor_name"] in fast else 50) for m in motors):
        raise RuntimeError("Mixed 50/500 Hz motor configuration changed")
    if {m["interface"] for m in motors} != {"kcan1", "kcan2", "kcan3", "kcan4"}:
        raise RuntimeError("Motor interfaces changed")
    return motors, contract["joint_names"]


def can_command(out, endpoint, joint_hash, duration):
    return [str(BASE / "candidates/xbox_native_turn120_20261019/sprite_can_xbox120"),
            "--config", str(UPPER / "motors.tsv"), "--kinematics-config", str(UPPER / "kinematics.tsv"),
            "--duration", str(duration), "--cpu", "5", "--realtime-priority", "50",
            "--output", str(out / "can.json"), "--ipc-socket", str(endpoint),
            "--policy-joint-hash", hex(joint_hash), "--bounded-shadow-preview",
            "--acknowledge-hardware-tx", "ZERO_GAIN_NATIVE_SHADOW", "--all-motors-disabled-confirmed"]


def producer_command(backend, seconds, output, interface=None, gpio=None):
    if backend == "openimu":
        if interface in {None, "kcan1", "kcan2", "kcan3", "kcan4"}:
            raise ValueError("Dedicated OpenIMU interface required")
        return [str(ROOT / "build/openimu/sprite_openimu"), "capture-canfd", interface, str(seconds), str(output)]
    if backend != "icm-spi" or gpio is None:
        raise ValueError("Explicit SPI GPIO required")
    chip, offset = gpio
    return [str(BASE / "candidates/icm_native_20261016/build/sprite_icm45686"), "capture",
            "/dev/spidev0.0", "/dev/" + chip, offset, "800", str(seconds), str(output),
            "X_DOWN_Z_BACK", "CONFIGURE_ICM45686_RAW_NO_CAN"]


def fixture(data, frames):
    if data[:8] != b"SPCHN001":
        raise ValueError("Require chain fixture")
    count = struct.unpack_from("<I", data, 8)[0]
    size = len(data) - count * 72 * 8
    if count < 1 or size < 12 or not 1 <= frames <= 6000:
        raise ValueError("Invalid fixture length/count")
    header = bytearray(data[:size])
    struct.pack_into("<I", header, 8, frames)
    return bytes(header), bytes(header) + bytes(frames * 72 * 8)


def openimu_report(path, expected_seconds):
    rows = np.atleast_1d(np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding="ascii"))
    if rows.size < 2:
        raise RuntimeError("Insufficient OpenIMU capture")
    tick = np.diff(rows["sensor_tick_us"].astype(np.int64)) & 65535
    kernel = rows["kernel_rx_ns"]
    gap = np.diff(kernel)
    age = rows["read_ns"] - rows["estimated_sample_ns"]
    elapsed = float(kernel[-1] - kernel[0]) / 1e9
    valid = (np.all((tick > 0) & (tick < 30000)) and np.all((gap >= 0) & (gap < 30000000))
             and np.all(rows["estimated_sample_ns"] > 0)
             and np.all(rows["estimated_sample_ns"] <= kernel) and np.all(kernel <= rows["read_ns"])
             and np.all((age >= 0) & (age < 30000000)))
    return dict(completed=bool(valid and elapsed >= expected_seconds - .1), samples=int(rows.size),
                host_elapsed_s=elapsed, host_sample_rate_hz=(rows.size - 1) / elapsed if elapsed > 0 else 0,
                sensor_delta_median_us=float(np.median(tick)), kernel_gap_max_ms=float(np.max(gap)) / 1e6,
                estimated_age_at_read_max_ms=float(np.max(age)) / 1e6,
                timestamp_order_valid=bool(valid), intrinsic_sensor_delay_measured=False)


def run(args, motors, joints):
    sys.path.insert(0, str(BASE / "candidates/icm_native_20261016/python"))
    from open_sprite_runtime.native_ipc import ordered_name_hash
    from open_sprite_runtime.native_imu_packet import decode_icm_packet

    no_running_runtime()
    for name in ("kcan1", "kcan2", "kcan3", "kcan4"):
        state = link(name)
        require_active(state)
        if state["linkinfo"]["info_data"].get("state") != "ERROR-ACTIVE":
            raise RuntimeError(name + " not ERROR-ACTIVE")
    adapter = None
    gpio = None
    if args.imu == "openimu":
        adapter = find_openimu("spriteimu0")
        require_active(link(adapter["interface"]))
    else:
        if Path("/sys/bus/platform/devices/3210000.spi/power/control").read_text().strip() != "on":
            raise RuntimeError("SPI PM must be on; use the scoped SPI PM wrapper")
        gpio = subprocess.check_output(["gpiofind", "PY.01"], text=True).split()
    (ROOT / "reports").mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="imu_client800_" + args.imu + "_", dir=ROOT / "reports"))
    print("REPORT_DIRECTORY", out, flush=True)
    print("ZERO GAIN ONLY. Keep still first 15s. No enable, zero reset, or nonzero motor command.", flush=True)
    frames = args.duration * 50
    header, data = fixture((CLIENT / "fixture120.bin").read_bytes(), frames)
    (out / "input.bin").write_bytes(data)
    (out / "names.txt").write_text("SPRITE_ZERO_GAIN_SHADOW_V1\n" + "\n".join(
        [m["motor_name"] for m in motors] + joints) + "\n")
    result = dict(passed=False, imu=args.imu, snapshot_period_us=1250, nominal_imu_hz=800,
                  policy_hz=50, ordinary_motor_hz=50, ankle_motor_hz=500, duration_s=args.duration,
                  command="stand only; no gamepad input in this shadow build", errors=[])
    processes = {}; handles = []
    def launch(name, command, env):
        log = (out / (name + ".log")).open("w"); handles.append(log)
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes[name] = proc
        result[name + "_command"] = command
        return proc
    def wait_socket(path, proc):
        deadline = time.monotonic() + 3
        while not path.is_socket():
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Producer socket unavailable: " + str(path))
            time.sleep(.01)
    try:
        with tempfile.TemporaryDirectory(prefix="sprite_imu800_") as tmp:
            imu_socket = Path(tmp) / "imu.sock"; state_socket = Path(tmp) / "state.sock"
            env = dict(os.environ, ICM_IPC_SOCKET=str(imu_socket), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
            imu = launch("imu", producer_command(args.imu, args.duration + 30, out / "imu.csv",
                         None if adapter is None else adapter["interface"], gpio), env)
            wait_socket(imu_socket, imu)
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.bind(str(Path(tmp) / "check.sock")); client.settimeout(.1)
                deadline = time.monotonic() + 25
                while True:
                    if imu.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("IMU stationary startup failed; see imu.log")
                    client.sendto(b"GETIMU01", str(imu_socket))
                    try:
                        packet = client.recv(193)
                    except socket.timeout:
                        continue
                    decode_icm_packet(packet, now_ns=time.monotonic_ns(), previous_sequence=0)
                    break
            print("IMU_READY: starting mixed-rate zero-gain CAN and native shadow actor", flush=True)
            can = launch("can", can_command(out, state_socket, ordered_name_hash(joints), args.duration), env)
            wait_socket(state_socket, can)
            actor = launch("actor", ["taskset", "-c", "4", str(SHADOW / "sprite_policy_imu800_shadow"),
                str(UPPER / "deploy/policy.onnx"), str(out / "input.bin"), str(out / "live.bin"),
                str(state_socket), str(imu_socket), str(out / "names.txt")], env)
            deadline = time.monotonic() + args.duration + 10
            while actor.poll() is None or can.poll() is None:
                if imu.poll() is not None:
                    raise RuntimeError("IMU exited before actor/CAN completed")
                if any(proc.poll() not in (None, 0) for proc in (actor, can)):
                    raise RuntimeError("Actor/CAN failed; see logs")
                if time.monotonic() > deadline:
                    raise RuntimeError("Actor/CAN timeout")
                time.sleep(.05)
            imu.wait(timeout=35)
            if any(proc.returncode != 0 for proc in (imu, can, actor)):
                raise RuntimeError("Nonzero child exit")
        can_report = json.loads((out / "can.json").read_text())
        imu_report = (openimu_report(out / "imu.csv", args.duration + 30) if args.imu == "openimu"
                      else json.loads((out / "imu.csv.json").read_text()))
        timing = np.atleast_1d(np.genfromtxt(out / "live.bin.timing", delimiter=",", names=True))
        consumed = (out / "live.bin.inputs").read_bytes()
        if len(consumed) != frames * 72 * 8 or timing.size != frames:
            raise RuntimeError("Incomplete policy frame count")
        (out / "consumed.bin").write_bytes(header + consumed)
        with (out / "offline.log").open("w") as log:
            subprocess.run([str(CLIENT / "sprite_policy_replay"), str(UPPER / "deploy/policy.onnx"),
                str(out / "consumed.bin"), str(out / "offline.bin")], stdout=log, stderr=subprocess.STDOUT, check=True)
        result.update(frames=frames, offline_byte_exact=(out / "live.bin").read_bytes() == (out / "offline.bin").read_bytes(),
                      can_report=can_report, imu_report=imu_report,
                      timing_ms={name: dict(median=float(np.median(timing[name])), p99=float(np.percentile(timing[name], 99)),
                                           maximum=float(np.max(timing[name]))) for name in timing.dtype.names})
        imu_ok = imu_report.get("completed") is True
        if args.imu == "icm-spi":
            imu_ok = imu_ok and imu_report["max_sample_gap_ns"] < 30_000_000
        result["passed"] = bool(result["offline_byte_exact"] and can_report.get("passed") is True and imu_ok
            and can_report.get("nonzero_gain_or_torque_tx_attempts") == 0 and can_report.get("automatic_enable_attempts") == 0
            and all(np.all(np.isfinite(timing[name])) for name in timing.dtype.names))
        if not result["passed"]:
            result["errors"].append("One or more existing qualification gates failed; no gates relaxed")
    except BaseException as exc:
        result["errors"].append(str(exc) or type(exc).__name__)
    finally:
        for proc in reversed(list(processes.values())):
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
        for proc in processes.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                result["passed"] = False; result["errors"].append("Child shutdown timed out")
        for handle in handles:
            handle.close()
        result["exit_codes"] = {name: proc.returncode for name, proc in processes.items()}
        (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result["passed"] else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    p.add_argument("--imu", required=True, choices=["openimu", "icm-spi"])
    p.add_argument("--duration", type=int, default=120, choices=[10, 120])
    p.add_argument("--confirm", choices=[ACK])
    args = p.parse_args()
    if not args.check and args.confirm != ACK:
        p.error("Confirm support, powered-but-disabled motors, and zero-gain queries using --confirm " + ACK)
    motors, joints = verify()
    if args.check:
        print("IMU800_SHADOW_CHECK_OK", args.imu, "NO HARDWARE; original walking scripts unchanged")
        return
    with (ROOT / ".openimu-session.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def interrupted(*_):
            raise KeyboardInterrupt("Shadow interrupted")
        signal.signal(signal.SIGTERM, interrupted)
        if args.imu == "icm-spi":
            # Reuse the SPI session lock and restore temporary PM changes on every exit.
            lock_path = Path("/run/lock/sprite_icm_spi_pm.lock")
            with lock_path.open("r" if lock_path.exists() else "a") as spi_lock:
                fcntl.flock(spi_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                no_running_runtime()
                pm = Path("/sys/bus/platform/devices/3210000.spi/power/control")
                previous = pm.read_text().strip()
                if previous != "on" and os.geteuid() != 0:
                    raise SystemExit("SPI PM is not on. Run this zero-gain wrapper with sudo; PM will be restored.")
                try:
                    if previous != "on":
                        pm.write_text("on\n")
                    raise SystemExit(run(args, motors, joints))
                finally:
                    if previous != "on":
                        pm.write_text(previous + "\n")
        raise SystemExit(run(args, motors, joints))


if __name__ == "__main__":
    main()
