"""Prepare isolated powered-test entries; never start sensors, CAN, or walking.

Reuse the reviewed mixed-rate admission with path-only substitutions, pin the
new actor and both completed zero-gain reports, and preserve baseline files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import os


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("Unexpected entry template: " + old)
    return text.replace(old, new)


def verify_hashes(entries):
    for name, expected in entries.items():
        if digest(Path(name)) != expected:
            raise RuntimeError("Input changed: " + name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = args.baseline.resolve(strict=True)
    old = base / "candidates/xbox_native_turn120_20261019"
    source = root / "candidates/imu_client800_20261124_v2"
    shadow = root / "candidates/imu_client800_shadow_20261124"
    upper = base / "candidates/upper_body_pd_wrist7_20261014"
    out = root / "candidates/imu_client800_powered_20261124"
    param = out / "parameters"
    if out.exists():
        raise SystemExit("Refuse to overwrite an existing candidate")
    subprocess.run([sys.executable, str(old / "check_powered_seal.py")], check=True)
    q = json.loads((source / "qualification.json").read_text())
    sq = json.loads((shadow / "qualification.json").read_text())
    if q.get("passed") is not True or sq.get("passed") is not True:
        raise RuntimeError("Offline qualification missing")
    verify_hashes({str(source / k): v for k, v in q["candidate_sha256"].items()})
    verify_hashes(q["baseline_sha256"])
    verify_hashes(sq["sha256"])
    evidence = {}
    for backend, folder in [("openimu", "imu_client800_openimu_dmwjye7_"),
                            ("icm-spi", "imu_client800_icm-spi_kbuupiep")]:
        path = root / "reports" / folder / "report.json"
        report = json.loads(path.read_text())
        can = report["can_report"]
        if (report.get("passed") is not True or report.get("offline_byte_exact") is not True
                or report.get("imu") != backend or report.get("snapshot_period_us") != 1250
                or report.get("frames") != 6000 or report.get("duration_s") != 120
                or report.get("actor_command", [])[3:4] != [str(shadow / "sprite_policy_imu800_shadow")]
                or can.get("passed") is not True or can.get("deadline_misses") != 0
                or can.get("nonzero_gain_or_torque_tx_attempts") != 0 or can.get("automatic_enable_attempts") != 0):
            raise RuntimeError("Required real-feedback shadow evidence missing: " + backend)
        evidence[str(path)] = digest(path)
    baseline_seal = json.loads((old / "powered_seal.json").read_text())
    upper_seal = json.loads((upper / "qualification/seal.json").read_text())
    verify_hashes(baseline_seal); verify_hashes(upper_seal)
    baseline_hashes = {**baseline_seal, **upper_seal,
                       str(upper / "kinematics.tsv"): digest(upper / "kinematics.tsv")}
    out.mkdir()
    result = dict(passed=False, hardware_access=False, powered_test_completed=False,
                  original_actor=str(old / "sprite_policy_xbox_powered"),
                  candidate_actor=str(out / "sprite_policy_xbox_powered"),
                  snapshot_period_us=1250, errors=[])
    try:
        shutil.copytree(source / "src", out / "src")
        for name in ("sprite_policy_xbox_powered", "sprite_policy_xbox_fake"):
            shutil.copy2(source / name, out / name)
        (out / "sprite_policy_xbox_fake_stop").symlink_to("sprite_policy_xbox_fake")
        (out / "qualification").symlink_to(source / "qualification", target_is_directory=True)
        for name in ("sprite_can_xbox120", "libonnxruntime.so.1"):
            (out / name).symlink_to((old / name).resolve(strict=True))
        for name in ("buttons_verified.json", "mapping_verified.json", "check_completion.py",
                     "gamepad_disable_probe", "gamepad_test", "test_options"):
            shutil.copy2(old / name, out / name)
        files = ["deploy/contract.json", "deploy/policy.onnx", "motors.tsv", "kinematics.tsv", "joint_safety.tsv",
                 "qualification/reference.json", "qualification/reference.npz", "qualification/fixture40.bin",
                 "qualification/seal.json", "qualification/parity/report.json"]
        files += ["qualification/" + name + "/report.json" for name in
                  ("fake_none", "fake_imu_freeze", "fake_state_disconnect")]
        for name in files:
            target = param / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(upper / name, target)
        substitutions = [(str(old), str(out)), (str(upper), str(param))]
        for name in ("admission.sh", "powered_adapter.py"):
            original = (old / name).read_text()
            text = original
            for before, after in substitutions:
                text = text.replace(before, after)
            restored = text
            for before, after in reversed(substitutions):
                restored = restored.replace(after, before)
            if restored != original:
                raise RuntimeError("Non-path admission or adapter change")
            # Keep separate report prefixes while retaining original preflight tools.
            if name == "admission.sh":
                text = replace_once(text, 'STAMP="icm_$(date +%Y%m%d_%H%M%S)"',
                                    'STAMP="imu800_$(date +%Y%m%d_%H%M%S)"')
            (out / name).write_text(text)
        inner_name = "run_sprite0825_xbox_native_turn120_inner.sh"
        outer_name = "run_sprite0825_xbox_native_turn120_on_253.sh"
        inner = (base / inner_name).read_text().replace(str(old), str(out))
        # The original qualification check still validates the unchanged baseline assets.
        inner = replace_once(inner, "[s]prite_icm45686|[s]prite_imu_", "[s]prite_openimu|[s]prite_icm45686|[s]prite_imu_")
        inner = inner.replace("reports/xbox_imu_turn120_", "reports/xbox_imu800_spi_")
        (out / inner_name).write_text(inner)
        outer = (base / outer_name).read_text()
        # --check returns before locking. Both real-backend entries share this lock.
        lock = ('exec 8>"' + str(root / ".openimu-session.lock") + '"\n'
                'flock -n 8 || { echo "Another IMU session is active"; exit 2; }\n')
        outer = replace_once(outer, "exec 9>/run/lock/sprite_icm_spi_pm.lock", lock + "exec 9>/run/lock/sprite_icm_spi_pm.lock")
        (out / outer_name).write_text(outer)
        receipt = dict(powered_test_completed=False, hardware_sha256=sq["sha256"],
                       evidence_sha256=evidence, baseline_sha256=baseline_hashes,
                       candidate_actor_sha256=digest(out / "sprite_policy_xbox_powered"))
        (out / "entry_receipts.json").write_text(json.dumps(receipt, indent=2) + "\n")
        checker = (old / "check_powered_seal.py").read_text()
        checker = replace_once(checker, "C=R/'candidates/xbox_native_turn120_20261019'", "C=Path(" + repr(str(out)) + ")")
        for name in (inner_name, outer_name):
            checker = replace_once(checker, "R/'" + name + "'", "C/'" + name + "'")
        checker = replace_once(checker, "buttons=json.loads", """receipt=json.loads((C/'entry_receipts.json').read_text())
for category in ('hardware_sha256','evidence_sha256','baseline_sha256'):
    for name,expected in receipt[category].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise SystemExit('800Hz prerequisite changed: '+name)
buttons=json.loads""")
        checker = replace_once(checker, "files+=list((C/'src').glob('*'))", """files+=list((C/'src').glob('*'))
    files+=list((C/'parameters').rglob('*'))
    files+=[C/'entry_receipts.json']
    files+=[Path(""" + repr(str(root / "tools/xbox_imu_session.py")) + "),Path(" + repr(str(root / "run_sprite0825_xbox_imu800_turn120_on_253.sh")) + ")]" )
        (out / "check_powered_seal.py").write_text(checker)
        for name in ("admission.sh", inner_name, outer_name):
            subprocess.run(["bash", "-n", str(out / name)], check=True)
        for name in ("powered_adapter.py", "check_powered_seal.py"):
            compile((out / name).read_text(), str(out / name), "exec")
        # Reproduce the admission's table exports offline, to local copies only.
        export = out / "export_check"; export.mkdir()
        env = dict(os.environ, PYTHONPATH=str(base / "candidates/icm_native_20261016/python"))
        for tool, options, name in [
            ("export_native_kinematics_config.py", ["--hardware", str(base / "config/hardware.sprite0825.kp110_kd5.json")], "kinematics.tsv"),
            ("export_native_joint_safety_config.py", ["--joint-limit-candidates", str(base / "artifacts/g60_model3450/reports/sprite0825_urdf_limit_candidates.json"),
                                                     "--gain-scale", "1.0", "--maximum-embedded-kd", "5.0"], "joint_safety.tsv")]:
            subprocess.run([sys.executable, str(base / "tools" / tool), "--contract", str(param / "deploy/contract.json"),
                            *options, "--output", str(export / name)], env=env, check=True)
            if digest(export / name) != digest(param / name):
                raise RuntimeError("Export differs from stable table: " + name)
        subprocess.run([sys.executable, str(out / "check_powered_seal.py"), "--seal"], check=True)
        subprocess.run(["bash", str(out / outer_name), "--check"], check=True)
        # The adapter's prepare-only branch has no socket or hardware operations.
        bundle_report = out / "bundle_check.json"
        command = [sys.executable, str(out / "powered_adapter.py"), "--prepare-only", "--socket", "/tmp/unused-state.sock",
            "--hardware-config", str(base / "config/hardware.sprite0825.kp110_kd5.json"),
            "--contract", str(param / "deploy/contract.json"), "--joint-limit-candidates",
            str(base / "artifacts/g60_model3450/reports/sprite0825_urdf_limit_candidates.json"),
            "--output", str(bundle_report), "--trace-output", str(out / "unused.npz"),
            "--native-imu-socket", "/tmp/unused-imu.sock", "--imu-source", "native-bno055",
            "--command-profile", "stand-walk010-stop-40s", "--gain-scale", "1.0", "--physical-startup-hold-seconds", "1.0",
            "--physical-startup-ramp-seconds", "5.0"]
        subprocess.run(command, check=True, env=dict(env, SPRITE_NATIVE_IMU_PROTOCOL="icm-v3"))
        bundle = Path(str(bundle_report) + ".native")
        live_fixture = (bundle / "input.bin").read_bytes()
        qualified_fixture = (source / "fixture120.bin").read_bytes()
        count = struct.unpack_from("<I", live_fixture, 8)[0]
        header_size = len(live_fixture) - count * 72 * 8
        if (count != 6001 or live_fixture[:header_size] != qualified_fixture[:header_size]
                or live_fixture[header_size:] != bytes(count * 72 * 8)):
            raise RuntimeError("New actor configuration differs from qualified offline fixture")
        for name in ("motors.tsv", "kinematics.tsv", "joint_safety.tsv"):
            if digest(bundle / name) != digest(upper / name):
                raise RuntimeError("Bundle parameter changed: " + name)
        verify_hashes(baseline_hashes)
        result["passed"] = True
    except BaseException as exc:
        result["errors"].append(str(exc) or type(exc).__name__)
        raise
    finally:
        (out / "entry_preparation.json").write_text(json.dumps(result, indent=2) + "\n")
    print("IMU800_ENTRY_PREPARED; same gains/limits/CAN; no hardware accessed; onsite powered approval required")


if __name__ == "__main__":
    main()
