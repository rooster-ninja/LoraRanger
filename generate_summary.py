#!/usr/bin/env python3
"""Generate the ping_esp32 project summary PDF."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = "ping_esp32_summary.pdf"

# ── Colour palette ────────────────────────────────────────────────────────────
DARK   = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#0f3460")
GOLD   = colors.HexColor("#e94560")
LIGHT  = colors.HexColor("#f5f5f5")
MID    = colors.HexColor("#cccccc")

def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        leftMargin=0.85*inch,
        rightMargin=0.85*inch,
        topMargin=0.9*inch,
        bottomMargin=0.9*inch,
    )

    base = getSampleStyleSheet()

    def sty(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    title_sty   = sty("Title2",   "Normal", fontSize=26, textColor=DARK,
                       fontName="Helvetica-Bold", spaceAfter=4, alignment=TA_CENTER)
    sub_sty     = sty("Sub",      "Normal", fontSize=11, textColor=ACCENT,
                       fontName="Helvetica", spaceAfter=2, alignment=TA_CENTER)
    h1_sty      = sty("H1",       "Normal", fontSize=14, textColor=ACCENT,
                       fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4)
    h2_sty      = sty("H2",       "Normal", fontSize=11, textColor=DARK,
                       fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=3)
    body_sty    = sty("Body2",    "Normal", fontSize=10, leading=15,
                       fontName="Helvetica", spaceAfter=4)
    bullet_sty  = sty("Bullet2",  "Normal", fontSize=10, leading=14,
                       fontName="Helvetica", leftIndent=16, spaceAfter=2,
                       bulletIndent=6, bulletFontName="Helvetica")
    mono_sty    = sty("Mono",     "Normal", fontSize=9, leading=13,
                       fontName="Courier", leftIndent=16, textColor=ACCENT)
    caption_sty = sty("Caption",  "Normal", fontSize=8, textColor=colors.grey,
                       fontName="Helvetica-Oblique", alignment=TA_CENTER)
    note_sty    = sty("Note",     "Normal", fontSize=9, leading=13,
                       fontName="Helvetica-Oblique", textColor=colors.HexColor("#555555"),
                       leftIndent=12, spaceAfter=4)

    def hr(): return HRFlowable(width="100%", thickness=0.5, color=MID, spaceAfter=6, spaceBefore=2)
    def sp(h=6): return Spacer(1, h)
    def h1(t): return Paragraph(t, h1_sty)
    def h2(t): return Paragraph(t, h2_sty)
    def p(t):  return Paragraph(t, body_sty)
    def b(t):  return Paragraph(f"• {t}", bullet_sty)
    def m(t):  return Paragraph(t, mono_sty)
    def note(t): return Paragraph(f"<i>{t}</i>", note_sty)

    # ── Pin table helper ──────────────────────────────────────────────────────
    def pin_table(rows, col_widths=None):
        if col_widths is None:
            col_widths = [1.1*inch, 1.1*inch, 3.6*inch]
        header = [
            Paragraph("<b>Pin</b>",      sty("th","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
            Paragraph("<b>GPIO</b>",     sty("th","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
            Paragraph("<b>Function</b>", sty("th","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
        ]
        data = [header] + [
            [Paragraph(a, mono_sty), Paragraph(b, mono_sty), Paragraph(c, body_sty)]
            for a, b, c in rows
        ]
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),  ACCENT),
            ("BACKGROUND",  (0,1), (-1,-1), LIGHT),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.3, MID),
            ("TOPPADDING",  (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
        ]))
        return t

    # ── Timing diagram as a simple table ─────────────────────────────────────
    def timing_table():
        w = [1.3*inch, 1.45*inch, 1.45*inch, 1.45*inch, 1.45*inch]
        data = [
            [Paragraph("<b>Event</b>",       sty("th2","Normal",fontSize=8,fontName="Helvetica-Bold",textColor=colors.white)),
             Paragraph("<b>Alpha GPIO4</b>", sty("th2","Normal",fontSize=8,fontName="Helvetica-Bold",textColor=colors.white)),
             Paragraph("<b>Alpha GPIO5</b>", sty("th2","Normal",fontSize=8,fontName="Helvetica-Bold",textColor=colors.white)),
             Paragraph("<b>Beta GPIO4</b>",  sty("th2","Normal",fontSize=8,fontName="Helvetica-Bold",textColor=colors.white)),
             Paragraph("<b>Notes</b>",       sty("th2","Normal",fontSize=8,fontName="Helvetica-Bold",textColor=colors.white))],
            ["Alpha TX", Paragraph("↑ pulse", mono_sty), "—", "—",        Paragraph("Ch1 trigger", body_sty)],
            ["Beta RX",  "—",                            "—", "—",        Paragraph("Packet received", body_sty)],
            ["Beta TX",  "—",                            "—", Paragraph("↑ pulse", mono_sty), Paragraph("Beta Ch1 trigger", body_sty)],
            ["Alpha RX", "—",                            Paragraph("↑ pulse", mono_sty), "—", Paragraph("Ch2 trigger — RTT complete", body_sty)],
            ["Idle",     "—",                            "—", "—",        Paragraph("Wait to ~1 s mark, repeat", body_sty)],
        ]
        t = Table(data, colWidths=w)
        t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
            ("GRID",           (0,0), (-1,-1), 0.3, MID),
            ("TOPPADDING",     (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
            ("LEFTPADDING",    (0,0), (-1,-1), 6),
            ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
        ]))
        return t

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    story = []

    # Title block
    story += [
        sp(10),
        Paragraph("ping_esp32", title_sty),
        Paragraph("LoRa Time-of-Flight Measurement System", sub_sty),
        Paragraph("Project Summary — v0.1", sty("ver","Normal",fontSize=9,
                  textColor=colors.grey,fontName="Helvetica",alignment=TA_CENTER)),
        sp(6),
        hr(),
        sp(4),
    ]

    # ── 1. Overview ───────────────────────────────────────────────────────────
    story += [
        h1("1. Overview"),
        p("Two Heltec Wireless Stick v3 devices (ESP32-S3 + SX1262) form a closed-loop "
          "LoRa link whose primary purpose is to measure the <b>Time of Flight (ToF)</b> "
          "of the radio signal between the two nodes."),
        p("<b>Alpha</b> transmits a minimum-size LoRa packet once per second and pulses "
          "GPIO4 at the instant of transmission. <b>Beta</b> replies immediately upon "
          "reception, pulsing its own GPIO4. Alpha pulses GPIO5 the instant it receives "
          "Beta's reply. A dual-channel oscilloscope captures both GPIO4 (Alpha Ch1) and "
          "GPIO5 (Alpha Ch2), giving a precise measurement of the total round-trip time "
          "(RTT). ToF is then derived from that RTT measurement by subtracting known "
          "components (see Section 5)."),
        sp(4),
    ]

    # ── 2. Hardware ───────────────────────────────────────────────────────────
    story += [
        h1("2. Hardware"),
        h2("2.1  Common specification (both nodes)"),
    ]
    hw_rows = [
        ("MCU",          "ESP32-S3",  "Xtensa LX7 dual-core, 240 MHz"),
        ("LoRa",         "SX1262",    "Semtech — 915 MHz band"),
        ("Firmware",     "Rust",      "no_std bare-metal via esp-hal 0.23"),
        ("Runtime",      "Embassy",   "async executor — esp-hal-embassy 0.6"),
        ("Flash tool",   "espflash",  "v4.4, --ignore-app-descriptor flag required"),
    ]
    hw_t = Table(
        [[Paragraph("<b>Item</b>", sty("th3","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Value</b>",sty("th3","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Notes</b>",sty("th3","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,mono_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty)] for a,b,c in hw_rows],
        colWidths=[1.1*inch, 1.3*inch, 3.4*inch],
    )
    hw_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [hw_t, sp(10)]

    story += [h2("2.2  SX1262 SPI pin assignment (identical on both nodes)")]
    story += [
        pin_table([
            ("SCK",    "GPIO9",  "SPI clock"),
            ("MOSI",   "GPIO10", "SPI data out"),
            ("MISO",   "GPIO11", "SPI data in"),
            ("NSS/CS", "GPIO8",  "Chip select — active low"),
            ("RST",    "GPIO12", "Hard reset"),
            ("BUSY",   "GPIO13", "Busy indicator (Wait trait)"),
            ("DIO1",   "GPIO14", "IRQ / TX-done / RX-done"),
            ("VEXT",   "GPIO21", "LoRa power rail enable — drive LOW"),
        ]),
        sp(10),
    ]

    story += [h2("2.3  Oscilloscope GPIO assignments")]
    story += [
        pin_table([
            ("Alpha GPIO4", "GPIO4", "Ch1 — pulse HIGH→LOW immediately before TX"),
            ("Alpha GPIO5", "GPIO5", "Ch2 — pulse HIGH→LOW on receipt of Beta's reply"),
            ("Beta GPIO4",  "GPIO4", "Ch1 — pulse HIGH→LOW immediately before Beta TX reply"),
        ]),
        note("GPIO4 and GPIO5 are unallocated on the Heltec Wireless Stick v3 header."),
        sp(8),
    ]

    # ── 3. LoRa Configuration ─────────────────────────────────────────────────
    story += [
        h1("3. LoRa Radio Configuration"),
    ]
    lora_rows = [
        ("Frequency",        "915 000 000 Hz",  "US 915 MHz ISM band"),
        ("Spreading Factor", "SF12",             "Maximum link budget (+6 dB vs SF11)"),
        ("Bandwidth",        "125 kHz",          "Narrowest BW — best sensitivity"),
        ("Coding Rate",      "4/8",              "Maximum FEC — most robust"),
        ("Preamble",         "8 symbols",        "Minimum reliable preamble"),
        ("Header",           "Explicit",         "Allows variable-length future payloads"),
        ("CRC",              "Enabled",          "Detects corrupted packets"),
        ("Output power",     "14 dBm",           "Adjustable; within regulatory limit"),
        ("Payload",          "1 byte (0x01)",    "Minimum LoRa payload — latency focus"),
        ("IQ inversion",     "Off",              "Peer-to-peer (not LoRaWAN gateway)"),
        ("Network",          "Private",          "No LoRaWAN sync word"),
    ]
    lora_t = Table(
        [[Paragraph("<b>Parameter</b>",sty("th4","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Value</b>",    sty("th4","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Rationale</b>",sty("th4","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty)] for a,b,c in lora_rows],
        colWidths=[1.5*inch, 1.5*inch, 2.85*inch],
    )
    lora_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [lora_t, sp(6),
              note("SF12 / BW125 gives a theoretical sensitivity of −137 dBm and an "
                   "air-time of ~2.8 s per packet. The 1-second loop period will stretch "
                   "to accommodate; adjust the timer once air-time is measured."),
              sp(8)]

    # ── 4. Software Architecture ──────────────────────────────────────────────
    story += [
        h1("4. Software Architecture"),
        h2("4.1  Firmware language & toolchain"),
        b("Language: Rust, <i>no_std</i> bare-metal (no OS, no heap allocator)"),
        b("HAL: esp-hal 0.23.1 — Heltec Wireless Stick v3 / ESP32-S3"),
        b("Async runtime: Embassy (esp-hal-embassy 0.6, embassy-executor 0.7)"),
        b("LoRa driver: lora-phy 3.0.1 (embedded-hal 1.0 / embedded-hal-async 1.0)"),
        b("SPI bridge: embedded-hal-bus 0.2 — ExclusiveDevice::new_no_delay()"),
        b("Flash: espflash 4.4 with --ignore-app-descriptor"),
        sp(8),

        h2("4.2  Key build notes"),
        b("App descriptor (EspAppDesc, 256 bytes, magic 0xABCD5432) is injected as the "
          "first symbol in .rodata via a custom rodata.x shadow — required by the "
          "ESP-IDF v5.5.1 bootloader efuse block revision check."),
        b("Linker: xtensa-esp32s3-elf-gcc (not the generic xtensa-esp-elf-gcc which "
          "defaults to big-endian)."),
        b("build.rs emits -Tlinkall.x and shadows rodata.x to guarantee descriptor "
          "placement."),
        b("Source environment before every build: source ~/export-esp.sh"),
        sp(8),

        h2("4.3  Alpha firmware flow"),
    ]

    alpha_steps = [
        ("Init",       "esp_hal::init → embassy init → VEXT LOW → SPI async → SX1262 init"),
        ("Loop start", "Wait until 1 s mark (embassy_time::Timer)"),
        ("TX pulse",   "GPIO4 HIGH → LOW  (oscilloscope Ch1 trigger)"),
        ("Transmit",   "lora.prepare_for_tx → lora.tx()  [payload: 0x01, 1 byte]"),
        ("Await RX",   "lora.prepare_for_rx → lora.rx()  [blocking wait for Beta reply]"),
        ("RX pulse",   "GPIO5 HIGH → LOW  (oscilloscope Ch2 — RTT measurement point)"),
        ("Repeat",     "Loop"),
    ]
    flow_t = Table(
        [[Paragraph("<b>Step</b>",   sty("fh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Action</b>", sty("fh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty)] for a,b in alpha_steps],
        colWidths=[1.1*inch, 4.75*inch],
    )
    flow_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [flow_t, sp(10)]

    story += [h2("4.4  Beta firmware flow")]
    beta_steps = [
        ("Init",      "Same hardware init as Alpha"),
        ("Listen",    "lora.prepare_for_rx → lora.rx()  [continuous listen]"),
        ("RX event",  "Packet received from Alpha"),
        ("TX pulse",  "GPIO4 HIGH → LOW  (oscilloscope Ch1 trigger)"),
        ("Reply",     "lora.prepare_for_tx → lora.tx()  [same 1-byte payload]"),
        ("Repeat",    "Return to Listen"),
    ]
    beta_t = Table(
        [[Paragraph("<b>Step</b>",   sty("fh2","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Action</b>", sty("fh2","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty)] for a,b in beta_steps],
        colWidths=[1.1*inch, 4.75*inch],
    )
    beta_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [beta_t, sp(10)]

    # ── 4.5 Software timing considerations ───────────────────────────────────
    story += [
        h2("4.5  Software timing considerations"),
        p("Consistent and deterministic firmware timing is critical to the accuracy of "
          "the ToF measurement. Every microsecond of jitter or drift in the firmware "
          "execution path between the RF event and the GPIO toggle directly adds error "
          "to the calibration offset and, ultimately, to the distance calculation. "
          "The firmware is therefore designed for efficiency and timing predictability "
          "at every stage of the TX/RX cycle."),
        sp(4),
    ]

    timing_considerations = [
        ("GPIO toggle placement",
         "Critical",
         "GPIO4 is toggled <b>immediately before</b> lora.prepare_for_tx() is called "
         "(Alpha/Beta). GPIO5 is toggled <b>immediately after</b> lora.rx() returns "
         "(Alpha). No processing, allocation, or logging occurs between the RF call "
         "and the GPIO toggle."),
        ("no_std bare-metal",
         "Critical",
         "No OS scheduler, no heap allocator, no dynamic dispatch. Execution is "
         "fully deterministic — there is no background task preempting the RF path."),
        ("Embassy async executor",
         "Important",
         "Embassy's single-threaded cooperative executor wakes on hardware IRQ "
         "(SX1262 DIO1 → GPIO14). Wake latency is bounded by the interrupt handler "
         "and executor poll cycle — typically sub-microsecond on ESP32-S3 at 240 MHz."),
        ("SX1262 DIO1 IRQ path",
         "Important",
         "lora-phy uses embedded-hal-async Wait on DIO1. The executor suspends the "
         "async task and resumes it on the rising edge of DIO1 (TX done / RX done). "
         "This is interrupt-driven — no polling loop adds variable delay."),
        ("No logging in hot path",
         "Important",
         "esp_println! (UART) is called <b>after</b> the GPIO toggle, never before. "
         "UART transmission is slow (~87 µs per byte at 115 200 baud) and would "
         "introduce significant jitter if placed inside the timing-critical path."),
        ("Consistent packet structure",
         "Important",
         "Alpha and Beta send identical 1-byte payloads with identical LoRa parameters. "
         "Air-time is therefore equal and symmetric — a requirement for the "
         "two-way ranging formula to cancel the air-time term cleanly."),
        ("Compiler optimisation",
         "Supporting",
         "Profile [dev] uses opt-level = 's' (size/speed balanced). Release builds "
         "use LTO + opt-level = 's'. Both avoid debug-mode overhead that could "
         "introduce variable instruction counts."),
        ("Known delay characterisation",
         "To be measured",
         "SX1262 internal TX ramp (~100 µs per datasheet) and RX acquisition latency "
         "are fixed hardware delays included in the calibration offset. They are "
         "consistent across packets and do not contribute jitter — only a fixed bias "
         "that calibration absorbs."),
    ]

    sw_t = Table(
        [[Paragraph("<b>Consideration</b>", sty("swh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Priority</b>",      sty("swh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Detail</b>",        sty("swh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty)] for a,b,c in timing_considerations],
        colWidths=[1.35*inch, 1.0*inch, 3.5*inch],
    )
    sw_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [
        sw_t,
        sp(4),
        note("The calibration step (Section 5.3) absorbs all consistent fixed delays "
             "into a single offset. What matters for accuracy is not the absolute value "
             "of each delay, but that each delay is <b>stable and repeatable</b> "
             "across measurement sessions. Firmware efficiency ensures this."),
        sp(8),
    ]

    # ── 5. ToF Measurement Methodology ───────────────────────────────────────
    story += [
        h1("5. Time-of-Flight Measurement Methodology"),

        h2("5.1  Signal timing diagram"),
        timing_table(),
        sp(6),

        h2("5.2  RTT decomposition"),
        p("The oscilloscope measures the elapsed time between the Alpha GPIO4 rising edge "
          "(Ch1 — packet transmission begins) and the Alpha GPIO5 rising edge "
          "(Ch2 — reply fully received). This total interval, called RTT, is composed of:"),
        sp(2),
    ]

    rtt_rows = [
        ("t_air_α",  "Alpha TX air-time",       "~2 793 ms",  "Calculable from LoRa parameters (see below)"),
        ("t_tof_αβ", "Propagation α → β",       "d / c",      "ToF one-way — what we want to measure"),
        ("t_air_β",  "Beta TX air-time",         "~2 793 ms",  "Identical packet structure → identical air-time"),
        ("t_tof_βα", "Propagation β → α",        "d / c",      "Equal to t_tof_αβ (symmetric path)"),
        ("t_proc",   "Beta processing latency",  "< 1 µs",     "Firmware responds immediately — negligible"),
    ]
    rtt_t = Table(
        [[Paragraph("<b>Symbol</b>",   sty("rh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Component</b>",sty("rh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Value</b>",    sty("rh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Notes</b>",    sty("rh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,mono_sty), Paragraph(b,body_sty),
          Paragraph(c,mono_sty), Paragraph(d,body_sty)] for a,b,c,d in rtt_rows],
        colWidths=[0.75*inch, 1.5*inch, 1.0*inch, 2.6*inch],
    )
    rtt_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [rtt_t, sp(8)]

    story += [
        h2("5.3  ToF extraction — calibration methodology"),
        p("The theoretical formula provides a starting model, but real measurements "
          "include both <b>known delays</b> (calculable from LoRa parameters) and "
          "<b>unknown delays</b> (firmware GPIO toggle latency, SX1262 TX/RX ramp "
          "timing, oscilloscope trigger jitter, PCB propagation). The approach is "
          "therefore empirical:"),
        sp(4),
    ]

    cal_rows = [
        ("Step 1", "Baseline at known distance",
         "Place Alpha and Beta at a precisely measured separation d₀ (e.g. 10 m, "
         "100 m). Record scope RTT₀."),
        ("Step 2", "Compute composite offset",
         "offset = RTT₀ − (2 × d₀ / c)  — absorbs 2× air-time plus all unknown "
         "fixed delays in one calibration constant."),
        ("Step 3", "Apply to unknown distance",
         "ToF = (RTT_measured − offset) / 2    →    d = ToF × c"),
        ("Step 4", "Validate",
         "Repeat at a second known distance to confirm the offset is stable. "
         "Adjust if systematic drift is observed."),
        ("Step 5", "Iterate",
         "Unknown delays (especially SX1262 internal latency) may vary with "
         "temperature or power state — field testing will characterise this."),
    ]
    cal_t = Table(
        [[Paragraph("<b>Step</b>",   sty("ch","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Action</b>", sty("ch","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Detail</b>", sty("ch","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,body_sty), Paragraph(c,body_sty)] for a,b,c in cal_rows],
        colWidths=[0.55*inch, 1.4*inch, 3.9*inch],
    )
    cal_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [cal_t, sp(6)]

    story += [
        h2("5.4  Delay budget — known vs unknown"),
    ]

    delay_rows = [
        ("LoRa air-time (×2)",        "Known",   "Calculated from SF/BW/CR/payload — ~5 586 ms total"),
        ("RF propagation (×2)",        "Unknown → measured", "d/c per leg — the quantity of interest"),
        ("SX1262 TX ramp-up",         "Partially known", "Datasheet spec ~100 µs; verify empirically"),
        ("SX1262 RX acquisition",     "Partially known", "Preamble detect latency; included in air-time calc"),
        ("Beta firmware response",    "Unknown → small", "Async task wake latency; target < 10 µs"),
        ("GPIO toggle jitter",        "Unknown → small", "esp-hal async GPIO; estimate < 1 µs"),
        ("Oscilloscope trigger error","Unknown → small", "Probe + trigger threshold; calibrate with loopback"),
    ]
    dl_t = Table(
        [[Paragraph("<b>Delay source</b>",  sty("dh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Status</b>",        sty("dh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Notes</b>",         sty("dh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty)] for a,b,c in delay_rows],
        colWidths=[1.7*inch, 1.45*inch, 2.7*inch],
    )
    dl_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [
        dl_t,
        sp(4),
        note("The calibration step (Step 2 above) lumps all unknown fixed delays into a "
             "single offset constant, eliminating the need to characterise each source "
             "individually — provided they remain stable across the measurement session."),
        sp(6),
        h2("5.5  Theoretical formula (reference)"),
        p("After calibration the working formula simplifies to:"),
        sp(2),
        Paragraph(
            "<b>ToF  =  ( RTT_measured  −  offset ) / 2</b>",
            sty("formula","Normal",fontSize=12,fontName="Courier-Bold",
                textColor=ACCENT,leftIndent=30,spaceBefore=4,spaceAfter=4),
        ),
        Paragraph(
            "<b>d  =  ToF × c        (c = 2.998 × 10⁸ m/s)</b>",
            sty("formula2","Normal",fontSize=12,fontName="Courier-Bold",
                textColor=GOLD,leftIndent=30,spaceBefore=2,spaceAfter=8),
        ),
        note("Methodology subject to field testing and refinement. All delay values "
             "above are estimates pending empirical characterisation."),
        sp(6),

        h2("5.6  Theoretical air-time at SF12 / BW125 / CR4-8 / 1-byte payload"),
    ]

    airtime_rows = [
        ("Symbol duration",    "T_s = 2¹² / 125 000",         "32.768 ms"),
        ("Preamble time",      "T_pre = (8 + 4.25) × T_s",    "401.4 ms"),
        ("Payload symbols",    "ceil formula (1-byte, CRC on)","varies ~70 symbols"),
        ("Payload time",       "~70 × T_s",                   "~2 294 ms"),
        ("Total air-time",     "T_pre + T_payload",            "≈ 2 793 ms  (2.793 s)"),
    ]
    at_t = Table(
        [[Paragraph("<b>Quantity</b>",  sty("ath","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Expression</b>",sty("ath","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Result</b>",    sty("ath","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,mono_sty)] for a,b,c in airtime_rows],
        colWidths=[1.5*inch, 2.5*inch, 1.85*inch],
    )
    at_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [at_t, sp(6)]

    story += [
        note("The oscilloscope RTT will therefore be ~5.6 s minimum (2 × 2.793 s) even "
             "at point-blank range. The 1-second loop timer must be extended to at least "
             "7 s to prevent overlapping packets."),
        sp(4),

        h2("5.7  Expected ToF values at typical ranges"),
    ]

    tof_rows = [
        ("100 m",   "0.33 µs",   "5 600.33 ms"),
        ("1 km",    "3.3 µs",    "5 606.6 ms"),
        ("10 km",   "33 µs",     "5 666 ms"),
        ("50 km",   "167 µs",    "5 934 ms"),
        ("100 km",  "333 µs",    "6 267 ms"),
    ]
    tof_t = Table(
        [[Paragraph("<b>Distance</b>",    sty("tfh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>One-way ToF</b>", sty("tfh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Expected RTT on scope</b>", sty("tfh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,mono_sty)] for a,b,c in tof_rows],
        colWidths=[1.2*inch, 1.5*inch, 3.15*inch],
    )
    tof_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [
        tof_t,
        sp(4),
        note("Oscilloscope time-base must resolve µs-level differences on top of a ~5.6 s "
             "window. Use a triggered single-shot capture or a math channel (Ch2 − Ch1) to "
             "zoom into the delta after subtracting the nominal 5 586 ms air-time offset."),
        sp(8),
    ]

    # ── 6. AD3 Oscilloscope Script ────────────────────────────────────────────
    story += [
        h1("6. Analog Discovery 3 — Automated ToF Reader"),
        p("The script <b>ad3_oscilloscope/ad3_tof_reader.py</b> automates RTT capture "
          "and ToF/distance calculation using the Digilent Analog Discovery 3. "
          "It requires Digilent WaveForms to be installed on the host machine "
          "(provides the <i>libdwf</i> C library) and runs in the dedicated Python "
          "venv at <b>ad3_oscilloscope/venv/</b>."),
        sp(6),
        h2("6.1  Hardware connections"),
    ]
    story += [
        pin_table([
            ("AD3 Ch1 (1+)", "Alpha GPIO4", "TX fired — oscilloscope Ch1 trigger"),
            ("AD3 Ch2 (2+)", "Alpha GPIO5", "Reply received — oscilloscope Ch2 trigger"),
            ("AD3 GND",      "Alpha GND",   "Common ground"),
        ]),
        sp(8),
        h2("6.2  Capture strategy — Record mode"),
        p("The AD3 has a 16K sample buffer. To cover the full 7+ second RTT window at "
          "a useful sample rate, the script uses DWF <b>Record mode</b> which streams "
          "data continuously beyond the buffer size."),
    ]

    capture_rows = [
        ("100 kS/s", "10 µs",   "0.16 s",  "50 samples", "Buffer too short"),
        ("10 kS/s",  "100 µs",  "1.6 s",   "5 samples",  "Buffer too short"),
        ("2 kS/s",   "500 µs",  "8.2 s ✓", "1 sample",   "Pulse barely visible"),
        ("10 kS/s + Record", "100 µs", "Unlimited ✓", "5 samples ✓", "Chosen approach"),
    ]
    cap_t = Table(
        [[Paragraph("<b>Rate</b>",     sty("cph","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Interval</b>", sty("cph","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Window</b>",   sty("cph","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Pulse width</b>", sty("cph","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Notes</b>",    sty("cph","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,mono_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty),
          Paragraph(d,mono_sty), Paragraph(e,body_sty)] for a,b,c,d,e in capture_rows],
        colWidths=[1.2*inch, 0.75*inch, 1.0*inch, 1.0*inch, 1.85*inch],
    )
    cap_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("BACKGROUND",     (0,-1),(-1,-1), colors.HexColor("#d4edda")),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [cap_t, sp(6),
              note("Sub-sample linear interpolation on the rising edge gives <100 µs "
                   "time resolution regardless of sample interval."),
              sp(8)]

    story += [h2("6.3  Usage")]
    usage_rows = [
        ("Step 1 — Calibrate",
         "venv/bin/python ad3_tof_reader.py --calibrate --distance 100 --count 20",
         "Run at known separation d₀. Outputs calibration offset."),
        ("Step 2 — Measure",
         "venv/bin/python ad3_tof_reader.py --offset <value> --count 20",
         "Run at unknown distance. Outputs ToF and distance."),
        ("With plots",
         "... --plot",
         "Adds raw capture plot + RTT distribution + distance histogram."),
    ]
    use_t = Table(
        [[Paragraph("<b>Mode</b>",    sty("uh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Command</b>", sty("uh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white)),
          Paragraph("<b>Output</b>",  sty("uh","Normal",fontSize=9,fontName="Helvetica-Bold",textColor=colors.white))]] +
        [[Paragraph(a,body_sty), Paragraph(b,mono_sty), Paragraph(c,body_sty)] for a,b,c in usage_rows],
        colWidths=[1.1*inch, 2.5*inch, 2.2*inch],
    )
    use_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, MID),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
        ("LEFTPADDING",    (0,0), (-1,-1), 6),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.white),
    ]))
    story += [use_t, sp(8)]

    # ── 7. Project file structure ─────────────────────────────────────────────
    story += [
        h1("7. Repository Layout"),
        m("LoraRanger/"),
        m("├── src/"),
        m("│   ├── main.rs              # Alpha firmware (TX node)"),
        m("│   ├── app_desc.rs          # ESP-IDF app descriptor (bootloader req.)"),
        m("│   └── bin/beta.rs          # Beta firmware (RX responder)"),
        m("├── ad3_oscilloscope/"),
        m("│   └── ad3_tof_reader.py    # AD3 automated RTT/ToF/distance script"),
        m("├── Cargo.toml               # Rust dependencies"),
        m("├── build.rs                 # Linker script injection + rodata.x shadow"),
        m("├── rust-toolchain.toml      # Pins to 'esp' Xtensa toolchain"),
        m("├── .cargo/config.toml       # Target, linker, espflash runner"),
        m("├── docs_venv/               # Python venv for PDF + notebook generation"),
        m("├── generate_summary.py      # This script"),
        m("├── generate_notebook.py     # Jupyter notebook generator"),
        m("└── ping_esp32_walkthrough.ipynb"),
        sp(8),
    ]

    # ── 8. Open items ─────────────────────────────────────────────────────────
    story += [
        h1("8. Open Items / Next Steps"),
        b("Verify VEXT pin (GPIO21) enables LoRa correctly on both physical boards."),
        b("Extend loop timer to ≥ 7 s to clear SF12 air-time (~5.6 s round-trip minimum)."),
        b("Calibrate AD3 baseline RTT at point-blank range using ad3_tof_reader.py --calibrate."),
        b("Validate calibration offset at a second known distance before field deployment."),
        b("Field test at increasing distances; plot ToF vs GPS-measured range."),
        b("Evaluate lower SF (e.g. SF9) to reduce air-time and improve µs-resolution of ToF delta."),
        b("Add RSSI/SNR logging via esp-println for link-quality correlation with range."),
        sp(20),
        hr(),
        Paragraph("ping_esp32 · Heltec Wireless Stick v3 · Rust no_std · 915 MHz SF12 · LoRa Time-of-Flight",
                  caption_sty),
    ]

    doc.build(story)
    print(f"PDF written → {OUTPUT}")

if __name__ == "__main__":
    build()
