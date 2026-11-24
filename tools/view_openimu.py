"""Display validated icm-v3 attitude only; no physical CAN, motor or policy access.

Run as a child of xbox_imu_session.py so a GUI crash cannot orphan the producer.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import tempfile
import time

MODEL = Path("/home/tony/sprite_runtime/sprite0825_stage2_g74_model3000_sim2real_candidate/"
             "assets/mujoco/sprite0825_v5_4340_shoulders/sprite0825_v5_external_pd.xml")


def body_attitude(sensor_quaternion):
    from open_sprite_runtime.imu import ImuMount, quaternion_wxyz_to_matrix, matrix_to_quaternion_wxyz
    mount = ImuMount.sprite0825_rear_pelvis().sensor_to_body_matrix
    rotation = quaternion_wxyz_to_matrix(sensor_quaternion) @ mount.T
    return matrix_to_quaternion_wxyz(rotation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, default=Path("/home/tony/open_sprite_runtime"))
    parser.add_argument("--mjcf", type=Path, default=MODEL)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--socket")
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.baseline_root / "candidates/icm_native_20261016/python"))
    from open_sprite_runtime.native_imu_packet import decode_icm_packet
    import mujoco
    import mujoco.viewer
    import numpy as np

    if not 1 <= args.duration <= 560:
        parser.error("duration must be 1..560s")
    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    free = np.flatnonzero(model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    if len(free) != 1:
        raise RuntimeError("Expected exactly one floating root")
    if args.check:
        print("VIEWER_CHECK_OK: model/dependencies only; no display or hardware access")
        return
    if not args.socket or args.report is None:
        parser.error("--socket and --report are required outside --check")
    if not os.environ.get("DISPLAY"):
        displays = sorted(Path("/tmp/.X11-unix").glob("X[0-9]*"))
        if len(displays) != 1:
            raise RuntimeError("Set DISPLAY to the logged-in desktop; cannot select one unambiguously")
        os.environ["DISPLAY"] = ":" + displays[0].name[1:]

    def interrupted(*_):
        raise KeyboardInterrupt("Viewer interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    data = mujoco.MjData(model)
    adr = int(model.jnt_qposadr[int(free[0])])
    data.qpos[adr:adr+3] = (0, 0, .65)
    report = dict(mode="openimu_attitude_only", motor_can_access=False, policy_execution=False,
                  frames=0, errors=[], display_completed=False, maximum_age_ms=0.0)
    viewer = None
    finish = None
    last_sequence = 0
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix="sprite_imu_view_") as folder, socket.socket(
                socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.bind(str(Path(folder) / "client.sock"))
            client.settimeout(.1)
            while finish is None or time.monotonic() < finish:
                if viewer is not None and not viewer.is_running():
                    report["stop_reason"] = "window_closed"
                    break
                client.sendto(b"GETIMU01", args.socket)
                packet = client.recv(193)
                now = time.monotonic_ns()
                decode_icm_packet(packet, now_ns=now, previous_sequence=last_sequence)
                sequence, sampled, _ = struct.unpack_from("<QQQ", packet, 8)
                last_sequence = sequence
                values = struct.unpack_from("<13d", packet, 80)
                quaternion = body_attitude(values[6:10])
                data.qpos[adr+3:adr+7] = quaternion
                mujoco.mj_forward(model, data)
                if viewer is None:
                    viewer = mujoco.viewer.launch_passive(model, data)
                    viewer.cam.lookat[:] = (0, 0, .55)
                    viewer.cam.distance = 1.8
                    viewer.cam.azimuth = 90
                    viewer.cam.elevation = -8
                    finish = time.monotonic() + args.duration
                    print("VIEW_READY: tilt forward/back, lean left/right, then rotate left/right slowly.", flush=True)
                    print("Absolute roll/pitch; yaw is relative to startup. Neutral joints; no motor CAN access.", flush=True)
                viewer.sync()
                w, x, y, z = quaternion
                roll = math.degrees(math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)))
                pitch = math.degrees(math.asin(max(-1, min(1, 2*(w*y-z*x)))))
                yaw = math.degrees(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))
                age = (now-sampled)/1e6
                records.append((now, sequence, age, roll, pitch, yaw))
                report["maximum_age_ms"] = max(report["maximum_age_ms"], age)
                report["frames"] += 1
                if report["frames"] % 50 == 1:
                    print(f"ATTITUDE roll={roll:+.2f} pitch={pitch:+.2f} yaw={yaw:+.2f} age_ms={age:.3f}", flush=True)
                time.sleep(.02)
            else:
                report["stop_reason"] = "display_duration_completed"
                report["display_completed"] = True
    except BaseException as exc:
        report["errors"].append(str(exc) or type(exc).__name__)
        report["stop_reason"] = "error"
    finally:
        if viewer is not None:
            viewer.close()
            time.sleep(.5)
        with args.report.with_suffix(".csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("host_ns", "sequence", "age_ms", "roll_deg", "pitch_deg", "yaw_deg"))
            writer.writerows(records)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
