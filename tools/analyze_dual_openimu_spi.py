"""Offline native-rate dual-IMU comparison; never writes runtime calibration."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def stats(values):
    values = np.asarray(values)
    return dict(min=float(np.min(values)), median=float(np.median(values)),
                p99=float(np.percentile(values, 99)), maximum=float(np.max(values)))


def body(raw):
    return -raw[:, [2, 1, 0]]


def integral_summary(time_s, velocity):
    dt = np.diff(time_s)
    mid = (velocity[1:] + velocity[:-1]) / 2
    increments = mid * dt
    cumulative = np.r_[0., np.cumsum(increments)]
    return dict(positive_deg=float(np.rad2deg(np.sum(np.maximum(increments, 0)))),
                negative_deg=float(np.rad2deg(np.sum(np.minimum(increments, 0)))),
                net_deg=float(np.rad2deg(cumulative[-1])),
                excursion_deg=float(np.rad2deg(np.ptp(cumulative))))


def tilt(acceleration):
    a = np.mean(acceleration, axis=0)
    return dict(body_accel_m_s2=a.tolist(),
                roll_deg=float(np.rad2deg(np.arctan2(a[1], a[2]))),
                pitch_deg=float(np.rad2deg(np.arctan2(-a[0], np.hypot(a[1], a[2])))))


def compare(folder):
    session = json.loads((folder / "session.json").read_text())
    op = np.genfromtxt(folder / "openimu.csv", names=True, delimiter=",")
    sp = np.genfromtxt(folder / "spi.csv", names=True, delimiter=",")
    if len(op) < 2 or len(sp) < 2:
        raise ValueError("Insufficient raw data")
    ticks = np.diff(op["sensor_tick_us"].astype(np.int64)) % 65536
    if np.any((ticks <= 0) | (ticks >= 30000)):
        raise ValueError("Ambiguous OpenIMU sample clock; refuse integration")
    sensor_time = np.r_[0., np.cumsum(ticks)*1e-6]
    raw = np.column_stack([op[name] for name in ("raw_gx", "raw_gy", "raw_gz")])
    scale = 2000*np.pi/180/32768
    uncorrected = body(raw*scale)
    bias_end = int(np.searchsorted(sensor_time, 15., side="left"))+1
    if bias_end > len(op):
        raise ValueError("No complete OpenIMU calibration window")
    bias = np.mean(uncorrected[:bias_end], axis=0)
    ow = uncorrected-bias
    sw = np.column_stack([sp[name] for name in ("wx_body", "wy_body", "wz_body")])
    oa = body(np.column_stack([op[name] for name in ("raw_ax", "raw_ay", "raw_az")])*4*9.80665/32768)
    sa = np.column_stack([sp[name] for name in ("ax_body", "ay_body", "az_body")])
    origin = min(op["estimated_sample_ns"][0], sp["event_ns"][0])
    ot = (op["estimated_sample_ns"]-origin)*1e-9
    st = (sp["event_ns"]-origin)*1e-9
    result = dict(acquisition_completed=session["acquisition_completed"], errors=session["errors"],
                  source_sha256={name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                                 for name in ("session.json", "openimu.csv", "spi.csv")},
                  samples=dict(openimu=len(op), spi=len(sp)),
                  openimu_tick_us=stats(ticks), openimu_non1250_tick_count=int(np.sum(ticks != 1250)),
                  openimu_rx_gap_ms=stats(np.diff(op["kernel_rx_ns"])*1e-6),
                  openimu_rx_to_read_ms=stats((op["read_ns"]-op["kernel_rx_ns"])*1e-6),
                  spi_sample_gap_ms=stats(np.diff(sp["event_ns"])*1e-6),
                  spi_edge_to_read_end_ms=stats((sp["read_end_ns"]-sp["event_ns"])*1e-6),
                  reconstructed_openimu_body_bias_rad_s=bias.tolist(), phases={})
    axes = dict(roll=0, pitch=1, yaw=2)
    complete = []
    for phase in session["phases"]:
        if "end_ns" not in phase:
            continue
        start, end = [(phase[key]-origin)*1e-9 for key in ("start_ns", "end_ns")]
        om = (ot >= start) & (ot <= end)
        sm = (st >= start) & (st <= end) & (sp["bias_ready"] == 1)
        if om.sum() < 2 or sm.sum() < 2:
            raise ValueError("Incomplete phase: "+phase["name"])
        entry = dict(openimu_samples=int(om.sum()), spi_samples=int(sm.sum()),
                     openimu_accel_tilt=tilt(oa[om]), spi_accel_tilt=tilt(sa[sm]),
                     openimu_mean_gyro=ow[om].mean(axis=0).tolist(), spi_mean_gyro=sw[sm].mean(axis=0).tolist())
        if phase["name"] in axes:
            axis = axes[phase["name"]]
            grid = np.arange(max(start+.06, ot[om][0], st[sm][0]), min(end-.06, ot[om][-1], st[sm][-1]), .002)
            x = np.column_stack([np.interp(grid, ot, ow[:, i]) for i in range(3)])
            y = np.column_stack([np.interp(grid, st, sw[:, i]) for i in range(3)])
            complete.append((x, y))
            vx, vy = x[:, axis], y[:, axis]
            correlation = float(np.corrcoef(vx, vy)[0, 1]) if np.std(vx)*np.std(vy) > 1e-12 else None
            rms = np.sqrt(np.mean(x*x, axis=0))
            slope = float(np.dot(vx, vy)/np.dot(vx, vx)) if np.dot(vx, vx) > 1e-12 else None
            lag_values = np.arange(-.05, .0501, .001)
            lag_error = [float(np.mean((vx-np.interp(grid+lag, st, sw[:, axis]))**2)) for lag in lag_values]
            best = int(np.argmin(lag_error))
            entry.update(axis=axis, dominant_openimu_axis=int(np.argmax(rms)),
                         correlation=correlation, spi_vs_openimu_slope=slope,
                         openimu_axis_rms_rad_s=rms.tolist(),
                         same_time_rmse_rad_s=float(np.sqrt(np.mean((vx-vy)**2))),
                         best_spi_time_shift_ms=float(lag_values[best]*1000),
                         best_shift_rmse_rad_s=float(np.sqrt(lag_error[best])),
                         openimu_hardware_time_integral=integral_summary(sensor_time[om], ow[om, axis]),
                         openimu_host_time_integral=integral_summary(ot[om], ow[om, axis]),
                         spi_integral=integral_summary(st[sm], sw[sm, axis]))
        result["phases"][phase["name"]] = entry
    if complete:
        x = np.concatenate([p[0] for p in complete])
        y = np.concatenate([p[1] for p in complete])
        matrix, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
        result["diagnostic_fit_only_not_applied"] = dict(row_vector_spi_equals_openimu_times=matrix.tolist(),
                                                        rank=int(rank),
                                                        condition=float(np.linalg.cond(x)),
                                                        residual_rms_rad_s=np.sqrt(np.mean((x@matrix-y)**2, axis=0)).tolist())
    result["limitations"] = [
        "Comparison is not independent physical ground truth or powered qualification.",
        "Host-aligned +/-50ms lag scan has 1ms grid and includes transport/timestamp effects; it is not intrinsic sensor delay.",
        "Per-axis gyro integrals are not exact Euler angle changes during coupled 3D movement.",
        "Motion-phase accelerometer tilt includes inertial acceleration; use still phases for pose comparison.",
        "No estimated rotation, scale, bias or delay is applied to runtime."]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = compare(args.folder)
    (args.folder/"comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
