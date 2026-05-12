```
          _____        H O N K !
        /`     `\     /
       /   ◉     \   /
      |            \=======,
      |             =======|
      |             =======|
      |            /=======`
       \          /
        `--------'
               | |
               | |
               | |
              /   \
             /     \

          g o o s e
```

# LoraRanger

A bare-metal Rust LoRa Time-of-Flight measurement system using two Heltec Wireless Stick v3 nodes (ESP32-S3 + SX1262). RF signal propagation time is measured via GPIO timing pulses captured on a dual-channel oscilloscope.

---

## Hardware

| Component | Detail |
|-----------|--------|
| MCU | ESP32-S3 (Xtensa LX7, 240 MHz) |
| LoRa | SX1262 — 915 MHz |
| Board | Heltec Wireless Stick v3 (× 2) |
| Firmware | Rust `no_std` bare-metal |
| Runtime | Embassy async executor |

### Pin Assignment (both nodes)

| Signal | GPIO | Function |
|--------|------|----------|
| SCK | 9 | SPI clock |
| MOSI | 10 | SPI data out |
| MISO | 11 | SPI data in |
| NSS/CS | 8 | Chip select |
| RST | 12 | SX1262 reset |
| BUSY | 13 | SX1262 busy |
| DIO1 | 14 | TX/RX done IRQ |
| VEXT | 21 | LoRa power (drive LOW) |

### Oscilloscope GPIO

| Pin | Node | Channel | Event |
|-----|------|---------|-------|
| GPIO4 | Alpha | Ch1 | Pulses before TX |
| GPIO5 | Alpha | Ch2 | Pulses on reply received (RTT complete) |
| GPIO4 | Beta | Ch1 | Pulses before TX reply |

---

## Nodes

### Alpha — `src/main.rs`
Initiates a ping every ~7.6 seconds. Pulses **GPIO4** (Ch1) immediately before transmitting, then pulses **GPIO5** (Ch2) the instant Beta's reply is received. The oscilloscope delta between Ch1 and Ch2 is the measured RTT.

### Beta — `src/bin/beta.rs`
Listens continuously. On receiving Alpha's packet, pulses **GPIO4** (Ch1) and replies immediately. No processing between receive and reply to minimise timing jitter.

---

## LoRa Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Frequency | 915 MHz | US ISM band |
| Spreading Factor | SF12 | Maximum link budget |
| Bandwidth | 125 kHz | Best sensitivity |
| Coding Rate | 4/8 | Maximum FEC |
| Payload | 1 byte | Minimum valid packet |
| Output power | 14 dBm | Within regulatory limit |
| Air-time | ~2 793 ms/packet | Calculated from parameters |

---

## Time-of-Flight Methodology

```
RTT  =  2 × t_air  +  2 × ToF
ToF  =  ( RTT − 2 × t_air ) / 2
d    =  ToF × c
```

### Calibration

Rather than relying purely on theoretical air-time, an empirical calibration is used:

1. Measure RTT₀ at a known separation d₀
2. Compute `offset = RTT₀ − 2 × (d₀ / c)` — absorbs air-time and all fixed firmware/radio delays in one constant
3. Apply `ToF = (RTT_measured − offset) / 2` → `d = ToF × c`
4. Validate at a second known distance

The calibration offset absorbs all stable fixed delays (SX1262 TX ramp ~100 µs, GPIO toggle latency, executor wake time) as long as they remain consistent across the session.

> **Note:** At SF12/BW125 the minimum RTT at point-blank range is ~5.6 s. The ToF contribution at 10 km is only ~66 µs above this baseline — oscilloscope µs-resolution measurement is required.

---

## Build & Flash

### Prerequisites

```bash
# Install Xtensa Rust toolchain (one-time)
cargo install espup && espup install

# Set environment (every new terminal)
source ~/export-esp.sh
```

### Flash Alpha
```bash
cargo run
```

### Flash Beta
```bash
cargo run --bin beta
```

---

## Analog Discovery 3 — ToF Reader

`ad3_oscilloscope/ad3_tof_reader.py` automates RTT capture and ToF/distance
calculation using the Digilent Analog Discovery 3.

**Requirements:** Digilent WaveForms installed (provides `libdwf`), AD3 connected via USB.

```
AD3 Ch1 (1+) → Alpha GPIO4   TX fired
AD3 Ch2 (2+) → Alpha GPIO5   reply received
AD3 GND      → Alpha GND
```

```bash
cd ad3_oscilloscope

# Set up environment (one-time)
python3 -m venv venv && venv/bin/pip install numpy matplotlib pydwf

# Step 1 — calibrate at a known distance
venv/bin/python ad3_tof_reader.py --calibrate --distance 100 --count 20

# Step 2 — measure at unknown distance (use offset from step 1)
venv/bin/python ad3_tof_reader.py --offset 5587.123456 --count 20

# With plots
venv/bin/python ad3_tof_reader.py --offset 5587.123456 --count 10 --plot
```

Captures at **10 kS/s** in Record mode (streams beyond the 16K buffer). The 500 µs
GPIO pulse appears as 5 samples; sub-sample linear interpolation gives <100 µs edge
resolution. Calibration absorbs `2×air-time + all fixed firmware/radio delays` into
one offset constant.

---

## Project Files

```
LoraRanger/
├── src/
│   ├── main.rs              # Alpha firmware (TX initiator)
│   ├── app_desc.rs          # ESP-IDF bootloader app descriptor
│   └── bin/
│       └── beta.rs          # Beta firmware (RX responder)
├── ad3_oscilloscope/
│   └── ad3_tof_reader.py    # AD3 automated RTT/ToF/distance capture script
├── Cargo.toml
├── Cargo.lock
├── build.rs                 # Linker script injection + rodata.x shadow
├── rust-toolchain.toml      # Pins to Xtensa 'esp' toolchain
├── .cargo/config.toml       # Target, linker, espflash runner
├── generate_summary.py      # Generates ping_esp32_summary.pdf
├── generate_notebook.py     # Generates Jupyter walkthrough notebook
└── ping_esp32_walkthrough.ipynb
```

---

## Documentation

| File | Description |
|------|-------------|
| `ping_esp32_summary.pdf` | Full project summary (generate with `docs_venv/bin/python3 generate_summary.py`) |
| `ping_esp32_walkthrough.ipynb` | Jupyter notebook — code walkthrough, air-time calculations, ToF methodology, live calibration calculator |

```bash
# Set up docs environment (one-time)
python3 -m venv docs_venv && docs_venv/bin/pip install reportlab jupyter matplotlib numpy

# Open notebook
docs_venv/bin/jupyter notebook ping_esp32_walkthrough.ipynb
```

---

## Known Build Notes

| Issue | Fix |
|-------|-----|
| Bootloader rejects image | `app_desc.rs` injects a valid `esp_app_desc_t` at start of `.rodata` via custom `rodata.x` |
| Linker endianness error | Use `xtensa-esp32s3-elf-gcc`, not `xtensa-esp-elf-gcc` |
| espflash app descriptor error | `--ignore-app-descriptor` flag in runner |
| `embassy-executor` version | Must be `0.7` — `esp-hal-embassy 0.6` generates `0.7` Spawner type |

---

*Heltec Wireless Stick v3 · Rust no_std · 915 MHz SF12 · LoRa Time-of-Flight*
