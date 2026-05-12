#!/usr/bin/env python3
"""Generate the ping_esp32 Jupyter notebook."""

import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.9.0"},
}

cells = []
md  = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

# ── helper: Rust code displayed as a fenced block ─────────────────────────────
def rust(label, src):
    return md(f"```rust\n// {label}\n{src.strip()}\n```")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 0. Title
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
# ping_esp32 — LoRa Time-of-Flight Measurement System
### Code Walkthrough Notebook
**Reference:** `ping_esp32_summary.pdf` (full project summary)

---

This notebook walks through the firmware for both nodes of the ping_esp32 system,
explains the LoRa radio configuration, derives the ToF measurement methodology,
and provides runnable calculations for air-time, expected RTT, and calibration.

| Node | Binary | Role |
|------|--------|------|
| **Alpha** | `cargo run` | Initiates ping, measures RTT via GPIO4/GPIO5 |
| **Beta** | `cargo run --bin beta` | Listens, replies immediately via GPIO4 |

> All calculations in this notebook are live Python — re-run cells to experiment
> with different SF / BW / distance values.
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Imports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("## 1 — Imports & Constants"))

cells.append(code("""\
import math
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Project constants (mirror firmware) ──────────────────────────────────────
FREQ_HZ      = 915_000_000   # 915 MHz
SF           = 12            # Spreading Factor
BW_KHZ       = 125          # Bandwidth kHz
CR           = 4             # Coding rate denominator (4/8 → CR=8 in lora-phy)
PREAMBLE     = 8             # preamble symbols
PAYLOAD_BYTES= 1             # 1-byte minimum packet
CRC          = True
EXPLICIT_HDR = True
TX_POWER_DBM = 14

C = 2.998e8   # speed of light m/s

print(f"Frequency  : {FREQ_HZ/1e6:.1f} MHz")
print(f"SF / BW    : SF{SF} / {BW_KHZ} kHz")
print(f"TX power   : {TX_POWER_DBM} dBm")
print(f"Payload    : {PAYLOAD_BYTES} byte")
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Hardware overview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 2 — Hardware (PDF § 2)

Both nodes use identical hardware — **Heltec Wireless Stick v3** (ESP32-S3 + SX1262).

### SX1262 SPI pin assignment
| Signal | GPIO | Notes |
|--------|------|-------|
| SCK    | 9    | SPI clock |
| MOSI   | 10   | SPI data out |
| MISO   | 11   | SPI data in |
| NSS/CS | 8    | Chip select, active low |
| RST    | 12   | Hard reset |
| BUSY   | 13   | Radio busy — implements async `Wait` trait |
| DIO1   | 14   | IRQ (TX done / RX done) — implements async `Wait` trait |
| VEXT   | 21   | LoRa power rail, drive **LOW** to enable |

### Oscilloscope GPIO assignments
| Pin | Node | Scope | Event |
|-----|------|-------|-------|
| GPIO4 | Alpha | Ch1 | Pulses immediately **before** Alpha TX |
| GPIO5 | Alpha | Ch2 | Pulses immediately **after** Beta reply received (RTT end) |
| GPIO4 | Beta  | Ch1 | Pulses immediately **before** Beta reply TX |

> GPIO4 and GPIO5 were chosen as unallocated pins on the Wireless Stick v3 header.
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. LoRa air-time calculation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 3 — LoRa Air-Time Calculation (PDF § 3 & § 5.6)

The air-time of each packet is a **known, deterministic delay** that dominates the
RTT budget. Accurate knowledge of it is essential for extracting the ToF signal.

The standard LoRa air-time formula (Semtech AN1200.13):
"""))

cells.append(code("""\
def lora_airtime_ms(sf, bw_khz, cr_denom, preamble, payload_bytes,
                    explicit_header=True, crc=True, low_dr_opt=None):
    \"\"\"
    Returns LoRa packet air-time in milliseconds.
    cr_denom: denominator of coding rate (e.g. 8 for 4/8)
    low_dr_opt: auto-detect if None (enabled when SF>=11 and BW<=125 kHz)
    \"\"\"
    bw_hz = bw_khz * 1000
    t_sym_ms = (2**sf / bw_hz) * 1000          # symbol duration (ms)

    # Low data-rate optimisation — mandatory for SF11/SF12 at BW125
    if low_dr_opt is None:
        low_dr_opt = (sf >= 11 and bw_khz <= 125)

    t_preamble_ms = (preamble + 4.25) * t_sym_ms

    # Payload symbol count
    h = 0 if explicit_header else 1
    de = 1 if low_dr_opt else 0
    n_pay = max(
        math.ceil(
            (8*payload_bytes - 4*sf + 28 + 16*int(crc) - 20*h)
            / (4 * (sf - 2*de))
        ) * cr_denom,
        0
    ) + 8

    t_payload_ms = n_pay * t_sym_ms
    return t_preamble_ms + t_payload_ms, t_sym_ms, n_pay


at_ms, t_sym_ms, n_pay = lora_airtime_ms(SF, BW_KHZ, CR, PREAMBLE, PAYLOAD_BYTES,
                                          EXPLICIT_HDR, CRC)

print(f"Symbol duration  : {t_sym_ms:.3f} ms")
print(f"Preamble time    : {(PREAMBLE + 4.25) * t_sym_ms:.1f} ms")
print(f"Payload symbols  : {n_pay}")
print(f"Payload time     : {n_pay * t_sym_ms:.1f} ms")
print(f"Total air-time   : {at_ms:.1f} ms  ({at_ms/1000:.3f} s)")
print(f"Round-trip (2×)  : {2*at_ms:.1f} ms  ({2*at_ms/1000:.3f} s)")
"""))

cells.append(code("""\
# Air-time across spreading factors (BW125, 1-byte payload)
sfs = range(7, 13)
airtimes = [lora_airtime_ms(sf, BW_KHZ, CR, PREAMBLE, PAYLOAD_BYTES)[0] for sf in sfs]

fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.bar([f"SF{sf}" for sf in sfs], airtimes, color="#0f3460", edgecolor="#e94560")
ax.axhline(at_ms, color="#e94560", linestyle="--", linewidth=1.2, label=f"SF{SF} = {at_ms:.0f} ms")
ax.set_ylabel("Air-time per packet (ms)")
ax.set_title("LoRa air-time vs Spreading Factor  |  BW 125 kHz, CR 4/8, 1-byte payload")
ax.legend()
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:.0f}"))
for bar, at in zip(bars, airtimes):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
            f"{at:.0f} ms", ha="center", va="bottom", fontsize=8)
plt.tight_layout()
plt.savefig("airtime_vs_sf.png", dpi=150)
plt.show()
print(f"\\nAt SF{SF}: each packet takes {at_ms:.1f} ms → round-trip minimum {2*at_ms:.1f} ms")
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. ToF methodology
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 4 — Time-of-Flight Methodology (PDF § 5)

### 4.1 RTT decomposition

The oscilloscope measures the time between:
- **Ch1 rising edge** (Alpha GPIO4) — packet transmission begins
- **Ch2 rising edge** (Alpha GPIO5) — Beta's reply fully received

This measured RTT breaks down as:

```
RTT = t_air_α  +  t_tof_αβ  +  t_air_β  +  t_tof_βα  +  t_proc
    ≈ 2 × t_air  +  2 × ToF
```

Since `t_air_α = t_air_β` (identical packet parameters) and `t_proc ≈ 0`
(Beta replies immediately in firmware).

### 4.2 Extraction formula

| Formula | Expression |
|---------|-----------|
| **ToF** | `( RTT_measured − 2 × t_air ) / 2` |
| **Distance** | `ToF × c` |

### 4.3 Calibration approach

Rather than computing `t_air` from theory alone, we use an **empirical calibration**:

1. Measure RTT₀ at known separation d₀
2. Compute `offset = RTT₀ − 2 × d₀ / c`  (absorbs air-time + all fixed firmware delays)
3. Apply: `ToF = (RTT_measured − offset) / 2` → `d = ToF × c`
4. Validate at a second known distance

This makes the result independent of unknown fixed delays (SX1262 ramp, GPIO jitter, etc.)
as long as they remain **stable** across the measurement session.
"""))

cells.append(code("""\
def tof_us(distance_m):
    \"\"\"One-way Time of Flight in microseconds.\"\"\"""
    return (distance_m / C) * 1e6

def expected_rtt_ms(distance_m, airtime_ms):
    \"\"\"Expected scope RTT in milliseconds at a given distance.\"\"\"""
    return 2 * airtime_ms + 2 * tof_us(distance_m) / 1000

distances_m = [0, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000]

print(f"{'Distance':>10}  {'One-way ToF':>14}  {'Expected RTT on scope':>22}  {'ToF as % of RTT':>16}")
print("-" * 68)
for d in distances_m:
    tof = tof_us(d)
    rtt = expected_rtt_ms(d, at_ms)
    pct = (2 * tof / 1000) / rtt * 100
    print(f"{d/1000:>9.1f}km  {tof:>12.2f} µs  {rtt:>20.1f} ms  {pct:>15.4f}%")
"""))

cells.append(code("""\
# Plot: expected scope RTT vs distance
dist_km = np.linspace(0, 100, 500)
rtt_ms_arr = [expected_rtt_ms(d * 1000, at_ms) for d in dist_km]
tof_ms_arr = [2 * tof_us(d * 1000) / 1000 for d in dist_km]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

# Left: absolute RTT
ax1.plot(dist_km, rtt_ms_arr, color="#0f3460", linewidth=2)
ax1.axhline(2 * at_ms, color="#e94560", linestyle="--", linewidth=1,
            label=f"Baseline 2×air-time = {2*at_ms:.0f} ms")
ax1.set_xlabel("Separation distance (km)")
ax1.set_ylabel("Expected RTT (ms)")
ax1.set_title("Scope RTT vs Distance")
ax1.legend(fontsize=8)
ax1.grid(True, alpha=0.3)

# Right: ToF component only (delta above baseline)
ax2.plot(dist_km, tof_ms_arr, color="#e94560", linewidth=2)
ax2.set_xlabel("Separation distance (km)")
ax2.set_ylabel("2 × ToF component (ms)")
ax2.set_title("ToF Signal above Baseline")
ax2.grid(True, alpha=0.3)
ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x*1000:.0f} µs" if x < 1 else f"{x:.2f} ms"))

plt.suptitle(f"SF{SF} / BW{BW_KHZ} kHz / CR4/{CR} — baseline RTT = {2*at_ms:.0f} ms", y=1.02)
plt.tight_layout()
plt.savefig("tof_vs_distance.png", dpi=150)
plt.show()
"""))

cells.append(md("""\
> **Key insight:** At SF12 / BW125, the ToF component is tiny relative to the
> total RTT (~0.006% at 100 km). The oscilloscope **must** measure with µs
> precision on top of a ~5.6 s window. Use a **math channel (Ch2 − Ch1)** or
> triggered single-shot capture, then subtract the known baseline offset.
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Software timing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 5 — Software Timing Considerations (PDF § 4.5)

Consistent, deterministic firmware execution is critical — any **jitter** in the
path between the RF event and the GPIO toggle appears as measurement noise.

| Consideration | Priority | Design decision in firmware |
|---|---|---|
| GPIO toggle placement | **Critical** | `pulse()` called **before** `prepare_for_tx()` (Alpha/Beta); **after** `lora.rx()` returns (Alpha) |
| `no_std` bare-metal | **Critical** | No OS scheduler, no heap allocator — execution is fully deterministic |
| Embassy async executor | **Important** | Wakes on DIO1 hardware IRQ (GPIO14). Sub-µs wake latency at 240 MHz |
| Logging after hot path | **Important** | `println!` is always **after** the GPIO pulse — UART (~87 µs/byte) must never precede it |
| Consistent packets | **Important** | Both nodes send identical 1-byte payloads → equal, symmetric air-times |
| Known fixed delays | **To calibrate** | SX1262 TX ramp (~100 µs), RX acquisition — stable biases absorbed by calibration offset |

### The calibration constant absorbs all stable fixed delays:
```
offset = RTT₀ − 2×(d₀/c)
       = 2×t_air + 2×t_ramp + 2×t_gpio_jitter + 2×t_executor_wake + ...
```
As long as each term is **stable** across the session, the offset is valid.
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Alpha firmware walkthrough
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 6 — Alpha Firmware Walkthrough (`src/main.rs`)

Alpha is the **initiator**. It transmits a 1-byte packet, waits for Beta's reply,
then toggles GPIO5 to mark the RTT completion point for the oscilloscope.

Flash with: `cargo run`
"""))

cells.append(md("""\
### 6.1 — Crate attributes and imports
"""))

cells.append(rust("src/main.rs — top of file", """\
#![no_std]   // no Rust standard library — bare metal
#![no_main]  // no Rust runtime entry point — esp_hal_embassy::main handles this

mod app_desc; // ESP-IDF app descriptor — required by bootloader efuse rev check

use embassy_executor::Spawner;
use embassy_time::{Delay, Duration, Timer};
use embedded_hal_bus::spi::ExclusiveDevice;
use esp_backtrace as _;       // panic handler → resets the chip
use esp_hal::{
    gpio::{Input, Level, Output, Pull},
    spi::master::Spi,
    timer::timg::TimerGroup,
};
use esp_println::println;     // UART serial output (115200 baud)
use lora_phy::{
    iv::GenericSx126xInterfaceVariant,
    mod_params::{Bandwidth, CodingRate, RxMode, SpreadingFactor},
    sx126x::{Config, Sx126x, Sx1262, TcxoCtrlVoltage},
    LoRa,
};
"""))

cells.append(md("""\
### 6.2 — GPIO pulse function

This is the timing-critical operation. It must be:
- **`#[inline(always)]`** — no function call overhead (call/ret ~1 ns each, but we eliminate even that)
- **No delay between high and low** — the rising edge alone is sufficient for oscilloscope triggering
- Called **before** `prepare_for_tx()` (Alpha/Beta TX) and **after** `lora.rx()` (Alpha RX)
"""))

cells.append(rust("pulse() — oscilloscope timing marker", """\
#[inline(always)]
fn pulse(pin: &mut Output<'_>) {
    pin.set_high();
    // No delay — rising edge triggers the oscilloscope
    // The pulse width is ~2 GPIO register writes ≈ a few nanoseconds
    pin.set_low();
}
"""))

cells.append(md("""\
### 6.3 — Initialisation sequence
"""))

cells.append(rust("main() — init", """\
#[esp_hal_embassy::main]
async fn main(_spawner: Spawner) {
    let p = esp_hal::init(esp_hal::Config::default());

    // Embassy timer — must be initialised before any Timer::after() or async GPIO
    let timg0 = TimerGroup::new(p.TIMG0);
    esp_hal_embassy::init(timg0.timer0);

    // VEXT: drive GPIO21 LOW to power the LoRa module and antenna circuit
    let _vext = Output::new(p.GPIO21, Level::Low);
    Timer::after(Duration::from_millis(100)).await; // wait for LoRa power rail to stabilise

    // Oscilloscope trigger outputs — idle LOW
    let mut tx_pin = Output::new(p.GPIO4, Level::Low); // Ch1 — TX fired
    let mut rx_pin = Output::new(p.GPIO5, Level::Low); // Ch2 — reply received
"""))

cells.append(md("""\
### 6.4 — SPI and SX1262 initialisation

Key design points:
- `Spi::new(..., Config::default())` — 1 MHz, Mode 0 (SPI config is `#[non_exhaustive]`, cannot use struct literal from outside the crate)
- `.into_async()` — converts to `Spi<'_, Async>` which implements `embedded_hal_async::spi::SpiBus` (required by lora-phy 3.x)
- `ExclusiveDevice::new_no_delay` — wraps the bus + CS into an `SpiDevice`; no inter-byte delay needed for SX1262
- `Input` pins implementing `embedded_hal_async::digital::Wait` — DIO1 and BUSY both use embassy GPIO interrupt, not polling
"""))

cells.append(rust("SPI + SX1262 setup", """\
    // SPI2 — 1 MHz, Mode 0, async (required by lora-phy)
    let spi_bus = Spi::new(p.SPI2, esp_hal::spi::master::Config::default())
        .unwrap()
        .with_sck(p.GPIO9)
        .with_mosi(p.GPIO10)
        .with_miso(p.GPIO11)
        .into_async();                      // Spi<'_, Async> → implements async SpiBus

    let spi = ExclusiveDevice::new_no_delay(
        spi_bus,
        Output::new(p.GPIO8, Level::High),  // CS — idle high
    ).unwrap();

    // GenericSx126xInterfaceVariant manages RST, DIO1 (Wait), BUSY (Wait)
    let iv = GenericSx126xInterfaceVariant::new(
        Output::new(p.GPIO12, Level::High), // RST — idle high
        Input::new(p.GPIO14, Pull::None),   // DIO1 — IRQ, implements async Wait
        Input::new(p.GPIO13, Pull::None),   // BUSY — implements async Wait
        None,                               // no dedicated RX antenna switch
        None,                               // no dedicated TX antenna switch
    ).unwrap();

    // LoRa::new performs radio reset + initialisation asynchronously
    let mut lora = LoRa::new(
        Sx126x::new(spi, iv, Config {
            chip: Sx1262,
            tcxo_ctrl: Some(TcxoCtrlVoltage::Ctrl1V7), // Heltec uses 1.7 V TCXO
            use_dcdc: true,                              // DC-DC converter enabled
            rx_boost: false,
        }),
        false,   // private network (not LoRaWAN)
        Delay,   // embassy_time::Delay — implements async DelayNs
    ).await.expect("LoRa init failed");
"""))

cells.append(md("""\
### 6.5 — Modulation and packet parameters
"""))

cells.append(rust("Modulation params — SF12 / BW125 / CR4-8", """\
    // SF12 / BW125 / CR4/8 — maximum link budget
    // Air-time: ~2 793 ms per packet (calculated in Section 3 of this notebook)
    let mdltn = lora.create_modulation_params(
        SpreadingFactor::_12,
        Bandwidth::_125KHz,
        CodingRate::_4_8,
        915_000_000,        // 915 MHz
    ).unwrap();

    // TX: 8-symbol preamble, explicit header, CRC on, IQ normal
    let mut tx_params = lora
        .create_tx_packet_params(8, false, true, false, &mdltn)
        .unwrap();

    // RX: same preamble/header, max payload = 1 byte (matches what Beta sends)
    let rx_params = lora
        .create_rx_packet_params(8, false, 1, true, false, &mdltn)
        .unwrap();
"""))

cells.append(md("""\
### 6.6 — Main loop (timing-critical section)

The ordering within each iteration is deliberate and must not be changed:
1. `pulse(tx_pin)` — scope trigger BEFORE any SPI activity
2. `prepare_for_tx` + `tx` — radio transmits
3. `prepare_for_rx(Single(255))` — arm for one reply (255 symbol timeout ≈ 8.36 s)
4. `lora.rx()` — blocks until Beta replies or timeout
5. `pulse(rx_pin)` — scope trigger IMMEDIATELY on return, before `println!`
6. `println!` — UART output, comes last (slow, must not precede steps 1-5)
"""))

cells.append(rust("Alpha main loop", """\
    let payload = [0x01u8]; // 1 byte — minimum valid LoRa payload
    let mut rx_buf = [0u8; 1];
    let mut seq: u32 = 0;

    loop {
        // ── TRANSMIT ──────────────────────────────────────────────────────
        pulse(&mut tx_pin);                         // Ch1 ↑↓  ToF start reference
        lora.prepare_for_tx(&mdltn, &mut tx_params, 14, &payload).await.unwrap();
        lora.tx().await.unwrap();                   // blocks until TX done IRQ

        // ── RECEIVE ───────────────────────────────────────────────────────
        // RxMode::Single(255): timeout = 255 symbols × 32.768 ms ≈ 8.36 s
        lora.prepare_for_rx(RxMode::Single(255), &mdltn, &rx_params).await.unwrap();

        match lora.rx(&rx_params, &mut rx_buf).await {
            Ok((_, status)) => {
                pulse(&mut rx_pin);                 // Ch2 ↑↓  ToF end reference (RTT complete)
                println!("#{} — reply received | RSSI {} dBm | SNR {} dB",
                    seq, status.rssi, status.snr);  // after pulse — UART is slow
            }
            Err(_) => {
                println!("#{} — RX timeout / error (no reply from Beta)", seq);
            }
        }

        seq = seq.wrapping_add(1);

        // 2 s gap — total cycle ≥ 7.6 s (2 × 2.793 s air-time + 2 s buffer)
        Timer::after(Duration::from_secs(2)).await;
    }
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Beta firmware walkthrough
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 7 — Beta Firmware Walkthrough (`src/bin/beta.rs`)

Beta is the **responder**. It stays in continuous receive mode and replies to every
packet from Alpha as fast as possible. The reply timing must be deterministic.

Flash with: `cargo run --bin beta`
"""))

cells.append(md("""\
### 7.1 — App descriptor path resolution

Because Beta lives in `src/bin/beta.rs`, the relative path to `app_desc.rs` uses `..`:
"""))

cells.append(rust("src/bin/beta.rs — app_desc path", """\
#[path = \"../app_desc.rs\"]  // resolves to src/app_desc.rs
mod app_desc;
// Required on every binary — the ESP-IDF v5.5.1 bootloader checks
// min_efuse_blk_rev_full from the first 256 bytes of .rodata
"""))

cells.append(md("""\
### 7.2 — Beta main loop

The reply sequence is timing-critical:
1. `lora.rx()` returns as soon as Alpha's packet is fully received (DIO1 IRQ)
2. `pulse(tx_pin)` — scope Ch1 trigger, **immediately** before the SPI commands
3. `prepare_for_tx` + `tx` — reply sent
4. `println!` — logging, always last
"""))

cells.append(rust("Beta main loop", """\
    loop {
        // ── LISTEN — continuous mode, no timeout ──────────────────────────
        lora.prepare_for_rx(RxMode::Continuous, &mdltn, &rx_params).await.unwrap();

        match lora.rx(&rx_params, &mut rx_buf).await {
            Ok((_, status)) => {
                // ── REPLY — as fast as possible ────────────────────────────
                pulse(&mut tx_pin);            // Ch1 ↑↓  Beta TX reference edge
                lora.prepare_for_tx(&mdltn, &mut tx_params, 14, &payload).await.unwrap();
                lora.tx().await.unwrap();

                // Logging strictly after TX — must never delay the pulse or SPI
                println!(\"Replied to Alpha | RSSI {} dBm | SNR {} dB\",
                    status.rssi, status.snr);
            }
            Err(_) => {
                println!(\"RX error — returning to listen\");
                Timer::after(Duration::from_millis(10)).await; // radio settle
            }
        }
    }
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Build notes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 8 — Build & Flash Notes (PDF § 4.2)

### Prerequisites
```bash
source ~/export-esp.sh          # sets LIBCLANG_PATH and Xtensa GCC in PATH
```

### Flash Alpha
```bash
cargo run                        # builds + flashes src/main.rs
```

### Flash Beta
```bash
cargo run --bin beta             # builds + flashes src/bin/beta.rs
```

### Known build requirements
| Requirement | Reason |
|-------------|--------|
| Linker: `xtensa-esp32s3-elf-gcc` (not `xtensa-esp-elf-gcc`) | Generic GCC defaults to big-endian; chip is little-endian |
| `build.rs` emits `-Tlinkall.x` | esp-hal does not emit this; without it interrupt vectors are unresolved |
| Custom `rodata.x` in `OUT_DIR` | Places `app_desc` first in `.rodata` — required by ESP-IDF v5.5.1 bootloader |
| `--ignore-app-descriptor` in runner | Suppresses espflash 4.x pre-flash check (bootloader on-chip still validates it) |
| `embassy-executor = "0.7"` (not 0.6) | `esp-hal-embassy 0.6` macro generates `0.7` `Spawner` type — mismatched versions cause type error |
"""))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Calibration calculator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cells.append(md("""\
## 9 — Live Calibration Calculator

Fill in your measured values to compute the calibration offset and convert
subsequent scope measurements to distance.
"""))

cells.append(code("""\
# ── EDIT THESE VALUES ────────────────────────────────────────────────────────
D0_M       = 100.0       # known calibration distance in metres
RTT0_MS    = 5793.0      # scope RTT measured at d0 (ms) — replace with your measurement

# ─────────────────────────────────────────────────────────────────────────────
offset_ms  = RTT0_MS - 2 * (D0_M / C) * 1000
print(f"Calibration distance  : {D0_M:.1f} m")
print(f"Measured RTT₀         : {RTT0_MS:.3f} ms")
print(f"Theoretical 2×ToF     : {2*(D0_M/C)*1000:.6f} ms  ({2*(D0_M/C)*1e6:.3f} µs)")
print(f"\\nCalibration offset    : {offset_ms:.3f} ms")
print(f"  (= 2×air-time + all fixed firmware/radio delays)")
print(f"  (theoretical 2×air-time = {2*at_ms:.3f} ms)")
print(f"  (residual unknown delays = {offset_ms - 2*at_ms:.3f} ms = {(offset_ms - 2*at_ms)*1000:.1f} µs)")

print("\\n── Apply to new measurements ───────────────────────────────────────")
test_measurements_ms = [RTT0_MS, RTT0_MS + 0.333, RTT0_MS + 0.667, RTT0_MS + 1.0]
for rtt in test_measurements_ms:
    tof_ms  = (rtt - offset_ms) / 2
    dist_m  = tof_ms / 1000 * C
    print(f"  RTT {rtt:.3f} ms → ToF {tof_ms*1000:.3f} µs → d = {dist_m:.1f} m")
"""))

cells.append(md("""\
---
*Generated by `generate_notebook.py` — re-run `docs_venv/bin/python3 generate_notebook.py` to rebuild.*

**Reference:** `ping_esp32_summary.pdf` | **Firmware:** `src/main.rs` (Alpha), `src/bin/beta.rs` (Beta)
"""))

# ── Build and save ─────────────────────────────────────────────────────────────
nb.cells = cells

OUTPUT = "ping_esp32_walkthrough.ipynb"
with open(OUTPUT, "w") as f:
    nbf.write(nb, f)
print(f"Notebook written → {OUTPUT}")
