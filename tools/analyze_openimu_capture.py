"""Audit a completed receive-only OpenIMU capture without accessing hardware."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def describe(values):
    ordered = sorted(values)
    def percentile(p):
        position = (len(ordered) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return dict(min=ordered[0], median=statistics.median(ordered), p99=percentile(.99),
                maximum=ordered[-1], mean=statistics.mean(ordered))


def analyze(folder):
    csv_path = folder / "imu.csv"
    session = json.loads((folder / "session.json").read_text())
    with csv_path.open(newline="") as stream:
        rows = [{key: int(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    if len(rows) < 2:
        raise ValueError("Need at least two samples")
    tick = [(b["sensor_tick_us"] - a["sensor_tick_us"]) & 65535 for a, b in zip(rows, rows[1:])]
    kernel = [(b["kernel_rx_ns"] - a["kernel_rx_ns"]) / 1e6 for a, b in zip(rows, rows[1:])]
    read_gap = [(b["read_ns"] - a["read_ns"]) / 1e6 for a, b in zip(rows, rows[1:])]
    age = [(r["read_ns"] - r["estimated_sample_ns"]) / 1e6 for r in rows]
    delay = [(r["read_ns"] - r["kernel_rx_ns"]) / 1e6 for r in rows]
    timestamps_valid = all(0 < r["estimated_sample_ns"] <= r["kernel_rx_ns"] <= r["read_ns"] for r in rows)
    elapsed_us = 0
    bias_end = None
    for i, dt in enumerate(tick, start=1):
        elapsed_us += dt
        if elapsed_us >= 15_000_000:
            bias_end = i + 1
            break
    if bias_end is None:
        raise ValueError("Capture shorter than the bias window")
    calibration = rows[:bias_end]
    scale = 2000 * math.pi / 180 / 32768
    bias = [statistics.mean(r[key] for r in calibration) * scale for key in ("raw_gx", "raw_gy", "raw_gz")]
    accel_scale = 4 * 9.80665 / 32768
    accel_norms = [math.sqrt(sum((r[key] * accel_scale)**2 for key in ("raw_ax", "raw_ay", "raw_az"))) for r in rows]
    gravity = session["ipc_check"]["mean_projected_gravity"]
    norm = math.sqrt(sum(v*v for v in gravity))
    horizontal = math.hypot(gravity[0], gravity[1])
    roll = math.degrees(math.atan2(-gravity[1], -gravity[2]))
    pitch = math.degrees(math.atan2(gravity[0], math.hypot(gravity[1], gravity[2])))
    result = dict(
        source_csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        source_session_sha256=hashlib.sha256((folder / "session.json").read_bytes()).hexdigest(),
        scope="completed receive-only test; no motor or powered qualification",
        session_passed=session["passed"], errors=session["errors"], samples=len(rows),
        host_capture_seconds=(rows[-1]["kernel_rx_ns"] - rows[0]["kernel_rx_ns"]) / 1e9,
        host_sample_rate_hz=(len(rows)-1)*1e9/(rows[-1]["kernel_rx_ns"] - rows[0]["kernel_rx_ns"]),
        hardware_tick_delta_us=describe(tick), non_1250us_tick_intervals=sum(t != 1250 for t in tick),
        hardware_counter_wraps=sum(b["sensor_tick_us"] < a["sensor_tick_us"] for a, b in zip(rows, rows[1:])),
        kernel_rx_gap_ms=describe(kernel), acquisition_gap_ms=describe(read_gap),
        kernel_rx_to_read_ms=describe(delay), estimated_age_at_read_ms=describe(age),
        timestamp_order_valid=timestamps_valid,
        reconstructed_first_15_sensor_seconds_bias_rad_s=bias,
        bias_note="Reconstructed from the first 15 sensor seconds; exact producer bias may include extra host-time samples.",
        raw_acceleration_norm_m_s2=describe(accel_norms), ipc_check=session["ipc_check"],
        mean_attitude=dict(roll_deg=roll, pitch_deg=pitch,
                           tilt_deg=math.degrees(math.acos(max(-1, min(1, -gravity[2]/norm)))),
                           horizontal_gravity_norm=horizontal,
                           existing_startup_horizontal_limit=.10,
                           mean_within_existing_startup_limit=horizontal <= .10),
        limitations=["Stationary capture cannot verify axis response during movement.",
                     "Host/kernel timing does not measure intrinsic sensor or firmware latency.",
                     "Mean tilt is not an evaluation of the actual future startup window."])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = analyze(args.folder)
    (args.folder / "timing_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
