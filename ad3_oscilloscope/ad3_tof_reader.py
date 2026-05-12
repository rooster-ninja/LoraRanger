#!/usr/bin/env python3
from __future__ import annotations
"""
LoraRanger — Analog Discovery 3 ToF Reader

Reads GPIO timing pulses from the Alpha node and computes
round-trip time, time-of-flight, and distance.

Hardware connections:
  AD3 Ch1 (1+) → Alpha GPIO4   TX fired marker        (oscilloscope Ch1)
  AD3 Ch2 (2+) → Alpha GPIO5   reply received marker  (oscilloscope Ch2)
  AD3 GND      → Alpha GND
  AD3 V+       → Beta VIN      5V power for Beta board (--power flag)
  AD3 GND      → Beta GND

Requires: WaveForms software installed (provides libdwf)
          pydwf, numpy, matplotlib  (pip install via this venv)

Usage:
  # Step 1 — calibrate at a known distance, powering Beta via AD3 V+
  python ad3_tof_reader.py --calibrate --distance 0.5 --count 10 --power

  # Step 2 — measure at unknown distance
  python ad3_tof_reader.py --offset <value from step 1> --count 20 --power

  # Plot a single raw capture to verify signal
  python ad3_tof_reader.py --plot --offset 0 --power
"""

import sys
import ctypes
import time
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Physical / firmware constants ─────────────────────────────────────────────
C_M_PER_MS  = 2.998e8 / 1000      # speed of light in m/ms
AIR_TIME_MS = 2793.0               # SF12 / BW125 / CR4-8 / 1-byte — per packet
PULSE_US    = 500                  # firmware pulse width (µs)

# ── Capture settings ──────────────────────────────────────────────────────────
SAMPLE_RATE_HZ  = 10_000           # 10 kS/s → 100 µs/sample → pulse = 5 samples
RECORD_TIME_S   = 10.0             # record window — covers full ~5.6+ s RTT
THRESHOLD_V     = 1.65             # 50% of 3.3 V — rising edge detection threshold
CHANNEL_RANGE_V = 5.0              # ±5 V input range

# ── DWF constants (from Digilent SDK) ────────────────────────────────────────
acqmodeRecord     = ctypes.c_int(3)
DwfStateDone      = ctypes.c_byte(2)

# ── AD3 power supply defaults ─────────────────────────────────────────────────
SUPPLY_VOLTAGE_V  = 5.0               # V+ rail voltage — 5V matches USB, board regulates to 3.3V
SUPPLY_WARMUP_S   = 1.5               # seconds to wait after enabling supply


def load_dwf():
    """Load the Digilent WaveForms dwf shared library."""
    if sys.platform == "darwin":
        lib = "/Applications/WaveForms.app/Contents/Frameworks/dwf.framework/dwf"
    elif sys.platform.startswith("win"):
        lib = "dwf"
    else:
        lib = "libdwf.so"
    try:
        return ctypes.cdll.LoadLibrary(lib)
    except OSError:
        print(f"ERROR: Could not load dwf library at '{lib}'.")
        print("       Install Digilent WaveForms: https://digilent.com/waveforms")
        sys.exit(1)


def open_device(dwf):
    """Open the first available Digilent device. Returns handle."""
    hdwf = ctypes.c_int()
    dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(hdwf))
    if hdwf.value == 0:
        szerr = ctypes.create_string_buffer(512)
        dwf.FDwfGetLastErrorMsg(szerr)
        print(f"ERROR: Could not open device: {szerr.value.decode()}")
        sys.exit(1)
    return hdwf


def enable_supply(dwf, hdwf, voltage=SUPPLY_VOLTAGE_V):
    """Enable AD3 V+ power supply at the given voltage (max 5V, 700mA)."""
    # Channel 0 = V+  Node 0 = enable,  Node 1 = voltage
    dwf.FDwfAnalogIOChannelNodeSet(hdwf, ctypes.c_int(0), ctypes.c_int(0), ctypes.c_double(1))
    dwf.FDwfAnalogIOChannelNodeSet(hdwf, ctypes.c_int(0), ctypes.c_int(1), ctypes.c_double(voltage))
    dwf.FDwfAnalogIOEnableSet(hdwf, ctypes.c_int(1))
    print(f"AD3 V+ supply enabled at {voltage:.1f} V — waiting {SUPPLY_WARMUP_S:.1f} s for board to boot...")
    time.sleep(SUPPLY_WARMUP_S)


def disable_supply(dwf, hdwf):
    """Disable AD3 V+ power supply."""
    dwf.FDwfAnalogIOEnableSet(hdwf, ctypes.c_int(0))
    print("AD3 V+ supply disabled.")


def configure_scope(dwf, hdwf):
    """Configure both analog channels for 3.3 V logic capture."""
    for ch in (0, 1):
        dwf.FDwfAnalogInChannelEnableSet(hdwf, ctypes.c_int(ch), ctypes.c_int(1))
        dwf.FDwfAnalogInChannelRangeSet(hdwf,  ctypes.c_int(ch), ctypes.c_double(CHANNEL_RANGE_V))
        dwf.FDwfAnalogInChannelOffsetSet(hdwf, ctypes.c_int(ch), ctypes.c_double(0.0))

    dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeRecord)
    dwf.FDwfAnalogInFrequencySet(hdwf,    ctypes.c_double(SAMPLE_RATE_HZ))
    dwf.FDwfAnalogInRecordLengthSet(hdwf, ctypes.c_double(RECORD_TIME_S))


def record_capture(dwf, hdwf, verbose=True):
    """
    Start a Record-mode capture and stream both channels into numpy arrays.
    Returns (ch1, ch2, time_axis_ms) or None on failure.
    """
    n_total = int(SAMPLE_RATE_HZ * RECORD_TIME_S)
    ch1 = np.zeros(n_total, dtype=np.float64)
    ch2 = np.zeros(n_total, dtype=np.float64)
    idx = 0

    # Start acquisition
    dwf.FDwfAnalogInConfigure(hdwf, ctypes.c_int(0), ctypes.c_int(1))

    if verbose:
        print(f"    Recording {RECORD_TIME_S:.0f} s at {SAMPLE_RATE_HZ/1000:.0f} kS/s ...", end=" ", flush=True)

    deadline = time.time() + RECORD_TIME_S + 5.0

    while idx < n_total:
        if time.time() > deadline:
            print("TIMEOUT")
            return None

        sts   = ctypes.c_byte()
        avail = ctypes.c_int()
        lost  = ctypes.c_int()
        corr  = ctypes.c_int()

        dwf.FDwfAnalogInStatus(hdwf, ctypes.c_int(1), ctypes.byref(sts))
        dwf.FDwfAnalogInStatusRecord(hdwf, ctypes.byref(avail), ctypes.byref(lost), ctypes.byref(corr))

        n = min(avail.value, n_total - idx)
        if n == 0:
            time.sleep(0.005)
            continue

        buf = (ctypes.c_double * n)()
        dwf.FDwfAnalogInStatusData(hdwf, ctypes.c_int(0), buf, ctypes.c_int(n))
        ch1[idx:idx + n] = buf[:n]
        dwf.FDwfAnalogInStatusData(hdwf, ctypes.c_int(1), buf, ctypes.c_int(n))
        ch2[idx:idx + n] = buf[:n]

        idx += n

    t_ms = np.arange(n_total) / SAMPLE_RATE_HZ * 1000
    return ch1, ch2, t_ms


def find_rising_edge_ms(signal: np.ndarray, t_ms: np.ndarray, threshold: float) -> float | None:
    """
    Return interpolated time (ms) of the first rising edge above threshold.
    Uses linear interpolation for sub-sample accuracy.
    """
    above = signal > threshold
    crossings = np.where(~above[:-1] & above[1:])[0]
    if len(crossings) == 0:
        return None
    i = crossings[0]
    # Linear interpolation between samples i and i+1
    v0, v1 = signal[i], signal[i + 1]
    frac = (threshold - v0) / (v1 - v0) if (v1 - v0) != 0 else 0.0
    return t_ms[i] + frac * (t_ms[1] - t_ms[0])


def plot_capture(ch1, ch2, t_ms, t1_ms=None, t2_ms=None, title=""):
    """Plot a single capture showing both channels and detected edges."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)

    for ax, sig, label, colour in zip(
        axes, [ch1, ch2],
        ["Ch1 — Alpha GPIO4 (TX fired)", "Ch2 — Alpha GPIO5 (reply received)"],
        ["#0f3460", "#e94560"]
    ):
        ax.plot(t_ms / 1000, sig, color=colour, linewidth=0.8, label=label)
        ax.axhline(THRESHOLD_V, color="grey", linestyle="--", linewidth=0.7, label=f"Threshold {THRESHOLD_V} V")
        ax.set_ylabel("Voltage (V)")
        ax.set_ylim(-0.5, 4.0)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)

    if t1_ms is not None:
        axes[0].axvline(t1_ms / 1000, color="#e94560", linewidth=1.2, label=f"Edge @ {t1_ms:.1f} ms")
    if t2_ms is not None:
        axes[1].axvline(t2_ms / 1000, color="#0f3460", linewidth=1.2, label=f"Edge @ {t2_ms:.1f} ms")

    axes[1].set_xlabel("Time (s)")
    fig.suptitle(title or f"LoraRanger — {RECORD_TIME_S:.0f} s capture @ {SAMPLE_RATE_HZ/1000:.0f} kS/s")
    plt.tight_layout()
    plt.savefig("last_capture.png", dpi=150)
    plt.show()


def run(args):
    dwf  = load_dwf()
    hdwf = open_device(dwf)

    if args.power:
        enable_supply(dwf, hdwf, args.voltage)

    configure_scope(dwf, hdwf)

    print(f"Analog Discovery 3 connected.")
    print(f"Sample rate : {SAMPLE_RATE_HZ/1000:.0f} kS/s  |  Window : {RECORD_TIME_S:.0f} s  |  Pulse width : {PULSE_US} µs")
    print(f"Threshold   : {THRESHOLD_V} V  |  Channel range : ±{CHANNEL_RANGE_V} V\n")

    rtts_ms = []

    for i in range(args.count):
        print(f"  [{i+1:02d}/{args.count:02d}] Waiting for Alpha TX pulse on Ch1 ...", end=" ", flush=True)

        result = record_capture(dwf, hdwf, verbose=False)
        if result is None:
            print("FAILED")
            continue

        ch1, ch2, t_ms = result

        t1 = find_rising_edge_ms(ch1, t_ms, THRESHOLD_V)
        t2 = find_rising_edge_ms(ch2, t_ms, THRESHOLD_V)

        if t1 is None:
            print("No Ch1 edge — check Alpha GPIO4 connection")
            continue
        if t2 is None:
            print(f"Ch1 @ {t1:.2f} ms — no Ch2 edge (Beta not replying?)")
            continue

        rtt = t2 - t1
        rtts_ms.append(rtt)
        print(f"RTT = {rtt:.3f} ms  (Ch1 @ {t1:.2f} ms, Ch2 @ {t2:.2f} ms)")

        if args.plot and i == 0:
            plot_capture(ch1, ch2, t_ms, t1, t2,
                         title=f"LoraRanger capture — RTT = {rtt:.3f} ms")

    if args.power:
        disable_supply(dwf, hdwf)
    dwf.FDwfDeviceClose(hdwf)

    if not rtts_ms:
        print("\nNo valid measurements collected.")
        return

    arr      = np.array(rtts_ms)
    rtt_mean = np.mean(arr)
    rtt_std  = np.std(arr)
    rtt_min  = np.min(arr)
    rtt_max  = np.max(arr)

    print(f"\n── Results ({len(rtts_ms)}/{args.count} valid captures) ─────────────────────────")
    print(f"  RTT mean  :  {rtt_mean:.3f} ms")
    print(f"  RTT std   :  {rtt_std:.4f} ms  ({rtt_std*1000:.1f} µs)")
    print(f"  RTT min   :  {rtt_min:.3f} ms")
    print(f"  RTT max   :  {rtt_max:.3f} ms")

    if args.calibrate:
        # ── Calibration ───────────────────────────────────────────────────────
        # offset absorbs 2×air-time + all fixed firmware/radio delays
        tof_2way_ms = 2.0 * (args.distance / C_M_PER_MS)
        offset      = rtt_mean - tof_2way_ms

        print(f"\n── Calibration ──────────────────────────────────────────────────")
        print(f"  Known distance      :  {args.distance:.2f} m")
        print(f"  Expected 2×ToF      :  {tof_2way_ms*1000:.4f} µs")
        print(f"  Calibration offset  :  {offset:.6f} ms")
        print(f"  Breakdown estimate  :  2×air-time ≈ {2*AIR_TIME_MS:.0f} ms + "
              f"fixed delays ≈ {(offset - 2*AIR_TIME_MS)*1000:.1f} µs")
        print(f"\n  ✓  Use this offset for measurement runs:")
        print(f"     python ad3_tof_reader.py --offset {offset:.6f} --count {args.count}")

    else:
        # ── Measurement ───────────────────────────────────────────────────────
        tof_ms   = (rtt_mean  - args.offset) / 2.0
        dist_m   = tof_ms * C_M_PER_MS
        tof_std  = rtt_std / 2.0
        dist_std = tof_std * C_M_PER_MS

        print(f"\n── Time-of-Flight & Distance ─────────────────────────────────────")
        print(f"  Calibration offset  :  {args.offset:.6f} ms")
        print(f"  ToF (one-way)       :  {tof_ms*1000:.4f} µs  ±  {tof_std*1000:.4f} µs")
        print(f"  Distance            :  {dist_m:.2f} m  ±  {dist_std:.2f} m")

        # ── Statistics plot ───────────────────────────────────────────────────
        if args.plot:
            tofs = [(r - args.offset) / 2.0 * 1000 for r in rtts_ms]
            dists = [t / 1000 * C_M_PER_MS for t in tofs]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
            ax1.plot(rtts_ms, "o-", color="#0f3460", markersize=4)
            ax1.axhline(rtt_mean, color="#e94560", linestyle="--", linewidth=1, label=f"Mean {rtt_mean:.3f} ms")
            ax1.set_xlabel("Capture #")
            ax1.set_ylabel("RTT (ms)")
            ax1.set_title("Round-Trip Time per capture")
            ax1.legend(fontsize=8)
            ax1.grid(True, alpha=0.3)

            ax2.hist(dists, bins=min(10, len(dists)), color="#0f3460", edgecolor="#e94560")
            ax2.axvline(dist_m, color="#e94560", linestyle="--", linewidth=1.2, label=f"Mean {dist_m:.1f} m")
            ax2.set_xlabel("Distance (m)")
            ax2.set_ylabel("Count")
            ax2.set_title("Distance distribution")
            ax2.legend(fontsize=8)
            ax2.grid(True, alpha=0.3)

            fig.suptitle(f"LoraRanger — {dist_m:.1f} m ± {dist_std:.1f} m")
            plt.tight_layout()
            plt.savefig("tof_results.png", dpi=150)
            plt.show()


def parse_args():
    p = argparse.ArgumentParser(
        description="LoraRanger — AD3 Time-of-Flight reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Calibrate at 100 m:
    python ad3_tof_reader.py --calibrate --distance 100 --count 20

  Measure at unknown distance:
    python ad3_tof_reader.py --offset 5587.123456 --count 20

  Plot a single capture + results:
    python ad3_tof_reader.py --offset 5587.123456 --count 5 --plot
""")
    p.add_argument("--calibrate",  action="store_true",
                   help="Calibration mode — compute offset at a known distance")
    p.add_argument("--distance",   type=float, default=None,
                   help="Known calibration distance in metres (required with --calibrate)")
    p.add_argument("--offset",     type=float, default=None,
                   help="Calibration offset in ms (from a prior --calibrate run)")
    p.add_argument("--count",      type=int,   default=10,
                   help="Number of captures to average (default: 10)")
    p.add_argument("--plot",       action="store_true",
                   help="Show plots (first raw capture + final results)")
    p.add_argument("--power",      action="store_true",
                   help="Enable AD3 V+ supply to power Beta board")
    p.add_argument("--voltage",    type=float, default=SUPPLY_VOLTAGE_V,
                   help=f"V+ supply voltage in volts (default: {SUPPLY_VOLTAGE_V}V)")

    args = p.parse_args()

    if args.calibrate and args.distance is None:
        p.error("--calibrate requires --distance <metres>")
    if not args.calibrate and args.offset is None:
        p.error("measurement mode requires --offset <ms>   (run --calibrate first)")

    return args


if __name__ == "__main__":
    run(parse_args())
