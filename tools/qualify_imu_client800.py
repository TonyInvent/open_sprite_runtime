"""Build an isolated shared-IMU actor and qualify it using fake peers only.

This does not install a powered entry, access sensors/CAN, or change the baseline.
Both SPI and OpenIMU use the same icm-v3 client in this actor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import os


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline = args.baseline.resolve(strict=True)
    original = baseline / "candidates/xbox_native_turn120_20261019"
    output = args.output.resolve()
    if output.exists() or output == baseline or baseline in output.parents:
        raise SystemExit("Use a new candidate directory outside the stable baseline")
    subprocess.run([sys.executable, str(original / "check_powered_seal.py")], check=True)
    include = baseline / "candidates/icm_native_20261016/native/src"
    old = (include / "policy_imu_client.hpp").read_text()
    new = (root / "native/src/policy_imu_client.hpp").read_text()
    addition = (
        "// SPI ICM45686 and CAN-FD OpenIMU both publish icm-v3 at nominal 800 Hz.\n"
        "// Keep acquisition asynchronous: policy snapshots must never wait for IPC.\n"
        "inline constexpr std::chrono::microseconds imu_snapshot_period(bool icm) {\n"
        "    return std::chrono::microseconds(icm ? 1250 : 5000);\n}\n"
    )
    restored = new.replace(addition, "").replace(
        "begin+imu_snapshot_period(icm_)", "begin+std::chrono::milliseconds(5)")
    if restored != old or new.count(addition) != 1:
        raise SystemExit("Unexpected baseline header difference; stop for review")
    output.mkdir(parents=True)
    report = dict(passed=False, hardware_access=False, powered_qualified=False,
                  backends=["openimu", "icm-spi"], snapshot_period_us=1250,
                  policy_hz=50, ordinary_motor_hz=50, ankle_motor_hz=500,
                  baseline=str(original), tests={}, errors=[])
    source_hashes = {}
    try:
        shutil.copytree(include, output / "include")
        shutil.copytree(original / "src", output / "src")
        # Quoted includes search the source directory before -I; pin the override there.
        shutil.copy2(root / "native/src/policy_imu_client.hpp", output / "src/policy_imu_client.hpp")
        shutil.copy2(root / "native/icm45686/client_test.cpp", output / "src/client_test.cpp")
        for path in [*original.joinpath("src").glob("*"), *include.glob("*"),
                     original / "fixture120.bin", original / "test_realtime.py"]:
            if path.is_file():
                source_hashes[str(path)] = digest(path)
        shutil.copy2(original / "fixture120.bin", output / "fixture120.bin")
        shutil.copy2(original / "test_realtime.py", output / "test_realtime.py")
        lib = Path(subprocess.check_output([sys.executable, "-c",
            "import onnxruntime,pathlib;print(pathlib.Path(onnxruntime.__file__).parent/'capi')"], text=True).strip())
        (output / "libonnxruntime.so.1").symlink_to(lib / "libonnxruntime.so.1.23.2")
        common = ["g++", "-std=c++17", "-O2", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-pthread",
                  "-I" + str(baseline / "build/policy_native_stage2/include"),
                  "-I" + str(output / "src"), "-I" + str(output / "include")]
        subprocess.run([*common, str(output / "src/client_test.cpp"), "-o", str(output / "imu_client_test")], check=True)
        result = subprocess.run([str(output / "imu_client_test")], capture_output=True, text=True)
        (output / "client_test.log").write_text(result.stdout + result.stderr)
        result.check_returncode()
        flags = ["-DSPRITE_LOOP_TEST", "-DSPRITE_POWERED_LOOP", "-DSPRITE_ICM_IMU_INPUT",
                 "-DSPRITE_GAMEPAD_INPUT", "-DSPRITE_XBOX_120", "-DSPRITE_XBOX_TURN", "-DSPRITE_GAMEPAD_STOP_COMBO"]
        source = str(output / "src/sprite_policy_replay.cpp")
        libs = [str(lib / "libonnxruntime.so.1.23.2"), "-Wl,-rpath,$ORIGIN"]
        for name, extra in [("sprite_policy_xbox_powered", flags),
                            ("sprite_policy_xbox_fake", [*flags, "-DSPRITE_GAMEPAD_FAKE_PEERS"]),
                            ("sprite_policy_replay", [])]:
            subprocess.run([*common, *extra, source, *libs, "-o", str(output / name)], check=True)
        model = baseline / "candidates/upper_body_pd_wrist7_20261014/deploy/policy.onnx"
        source_hashes[str(model)] = digest(model)
        env = dict(os.environ, PYTHONPATH=str(baseline / "candidates/icm_native_20261016/python"),
                   SPRITE_GAMEPAD_DEVICE="/fake/no-hardware", SPRITE_GAMEPAD_FORWARD_SIGN="-1",
                   SPRITE_GAMEPAD_TURN_SIGN="-1")
        for fault in ("none", "imu_freeze", "state_disconnect", "operator_disable"):
            print("FAKE_PEERS_ONLY", fault, flush=True)
            target = output / "qualification" / fault
            subprocess.run([sys.executable, str(output / "test_realtime.py"),
                "--binary", str(output / "sprite_policy_xbox_fake"),
                "--offline-binary", str(output / "sprite_policy_replay"), "--model", str(model),
                "--fixture", str(output / "fixture120.bin"), "--output-dir", str(target),
                "--fault", fault, "--command-profile", "xbox-turn120", "--powered-candidate", "--icm-input"],
                check=True, env=env)
            report["tests"][fault] = json.loads((target / "report.json").read_text())
        if any(digest(Path(path)) != sha for path, sha in source_hashes.items()):
            raise RuntimeError("Stable source changed during qualification")
        subprocess.run([sys.executable, str(original / "check_powered_seal.py")], check=True)
        report["passed"] = True
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
        raise
    finally:
        report["baseline_sha256"] = source_hashes
        report["candidate_sha256"] = {str(path.relative_to(output)): digest(path)
            for path in output.rglob("*") if path.is_file() and path.name != "qualification.json"}
        (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("IMU_CLIENT800_OFFLINE_PASSED: both backends; no hardware; NOT powered-qualified", flush=True)


if __name__ == "__main__":
    main()
