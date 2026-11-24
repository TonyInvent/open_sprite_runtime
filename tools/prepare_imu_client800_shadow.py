"""Build and fake-peer-qualify a zero-gain-only actor from the reviewed candidate."""
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


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Unexpected fake-peer harness; review before adaptation: " + old)
    return text.replace(old, new)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--baseline", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    args = p.parse_args()
    c = args.candidate.resolve(strict=True)
    b = args.baseline.resolve(strict=True)
    out = args.output.resolve()
    if out.exists() or out == b or b in out.parents or out == c or c in out.parents:
        raise SystemExit("Require a fresh isolated output directory")
    q = json.loads((c / "qualification.json").read_text())
    if q.get("passed") is not True or q.get("snapshot_period_us") != 1250:
        raise SystemExit("Shared-client offline qualification missing")
    for name, sha in q["candidate_sha256"].items():
        if digest(c / name) != sha:
            raise SystemExit("Candidate changed: " + name)
    for name, sha in q["baseline_sha256"].items():
        if digest(Path(name)) != sha:
            raise SystemExit("Baseline changed: " + name)
    out.mkdir(parents=True)
    shutil.copytree(c / "src", out / "src")
    shutil.copytree(c / "include", out / "include")
    report = dict(passed=False, hardware_access=False, powered_qualified=False, tests={}, errors=[])
    try:
        (out / "libonnxruntime.so.1").symlink_to((c / "libonnxruntime.so.1").resolve())
        cmd = ["g++", "-std=c++17", "-O2", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-pthread",
               "-DSPRITE_LOOP_TEST", "-DSPRITE_SHADOW_LOOP", "-DSPRITE_ICM_IMU_INPUT",
               "-I" + str(out / "src"), "-I" + str(out / "include"),
               "-I" + str(b / "build/policy_native_stage2/include"),
               str(out / "src/sprite_policy_replay.cpp"), str((c / "libonnxruntime.so.1").resolve()),
               "-Wl,-rpath,$ORIGIN", "-o", str(out / "sprite_policy_imu800_shadow")]
        subprocess.run(cmd, check=True)
        # Same reviewed harness; only the IPC contract changes to shadow-only.
        harness = (c / "test_realtime.py").read_text()
        harness = replace_once(harness, "SPRITE_POWERED_WALK40_V1", "SPRITE_ZERO_GAIN_SHADOW_V1")
        harness = replace_once(harness, "profile_args=[str(names),args.command_profile,ack]", "profile_args=[str(names)]")
        harness = replace_once(harness,
            "ipc_matches=ipc_matches and np.array_equal(row['protected'],transmitted)",
            "expected=row['protected'].copy();expected[1:]=0\n            ipc_matches=ipc_matches and np.array_equal(expected,transmitted)")
        (out / "test_shadow_fake.py").write_text(harness)
        model = b / "candidates/upper_body_pd_wrist7_20261014/deploy/policy.onnx"
        env = dict(os.environ, PYTHONPATH=str(b / "candidates/icm_native_20261016/python"))
        for fault in ("none", "imu_freeze", "state_disconnect"):
            target = out / "fake" / fault
            subprocess.run([sys.executable, str(out / "test_shadow_fake.py"),
                "--binary", str(out / "sprite_policy_imu800_shadow"), "--offline-binary", str(c / "sprite_policy_replay"),
                "--model", str(model), "--fixture", str(c / "fixture120.bin"), "--output-dir", str(target),
                "--fault", fault, "--command-profile", "xbox-turn120", "--powered-candidate", "--icm-input"],
                check=True, env=env)
            report["tests"][fault] = json.loads((target / "report.json").read_text())
        upper = b / "candidates/upper_body_pd_wrist7_20261014"
        sealed = json.loads((upper / "qualification/seal.json").read_text())
        pinned = [upper / "deploy/contract.json", model, upper / "motors.tsv"]
        for path in pinned:
            if digest(path) != sealed[str(path)]:
                raise RuntimeError("Deployment asset changed: " + str(path))
        paths = [*pinned, upper / "kinematics.tsv", c / "sprite_policy_replay", c / "fixture120.bin",
                 out / "sprite_policy_imu800_shadow", out / "src/policy_imu_client.hpp",
                 b / "candidates/xbox_native_turn120_20261019/sprite_can_xbox120",
                 b / "candidates/icm_native_20261016/build/sprite_icm45686",
                 c.parents[1] / "build/openimu/sprite_openimu"]
        report["sha256"] = {str(path): digest(path) for path in paths}
        report["compile_command"] = cmd
        report["passed"] = True
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
        raise
    finally:
        (out / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("SHADOW_ACTOR_QUALIFIED: fake IPC verified zero Kp/Kd/velocity/feedforward; no hardware")


if __name__ == "__main__":
    main()
