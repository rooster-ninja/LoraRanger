// Alpha — LoRa ToF transmitter
// GPIO4: pulses before TX (oscilloscope Ch1)
// GPIO5: pulses on RX reply received (oscilloscope Ch2)
// cargo run

#![no_std]
#![no_main]

mod app_desc;

use embassy_executor::Spawner;
use embassy_time::{Delay, Duration, Timer};
use embedded_hal_bus::spi::ExclusiveDevice;
use esp_backtrace as _;
use esp_hal::{
    gpio::{Input, Level, Output, Pull},
    spi::master::Spi,
    timer::timg::TimerGroup,
};
use esp_println::println;
use lora_phy::{
    iv::GenericSx126xInterfaceVariant,
    mod_params::{Bandwidth, CodingRate, RxMode, SpreadingFactor},
    sx126x::{Config, Sx126x, Sx1262, TcxoCtrlVoltage},
    LoRa,
};

const LORA_FREQUENCY_HZ: u32 = 915_000_000;

// Pulse a pin high then low — oscilloscope timing marker
// Placed inline to keep the hot path as deterministic as possible
#[inline(always)]
fn pulse(pin: &mut Output<'_>) {
    pin.set_high();
    pin.set_low();
}

#[esp_hal_embassy::main]
async fn main(_spawner: Spawner) {
    let p = esp_hal::init(esp_hal::Config::default());

    let timg0 = TimerGroup::new(p.TIMG0);
    esp_hal_embassy::init(timg0.timer0);

    // Power LoRa module via VEXT (active low)
    let _vext = Output::new(p.GPIO21, Level::Low);
    Timer::after(Duration::from_millis(100)).await;

    // Oscilloscope trigger outputs
    let mut tx_pin = Output::new(p.GPIO4, Level::Low); // Ch1 — TX fired
    let mut rx_pin = Output::new(p.GPIO5, Level::Low); // Ch2 — reply received

    // SPI2 — async mode required by lora-phy
    let spi_bus = Spi::new(p.SPI2, esp_hal::spi::master::Config::default())
        .unwrap()
        .with_sck(p.GPIO9)
        .with_mosi(p.GPIO10)
        .with_miso(p.GPIO11)
        .into_async();
    let spi = ExclusiveDevice::new_no_delay(
        spi_bus,
        Output::new(p.GPIO8, Level::High),
    )
    .unwrap();

    // SX1262 control pins
    let iv = GenericSx126xInterfaceVariant::new(
        Output::new(p.GPIO12, Level::High), // RST
        Input::new(p.GPIO14, Pull::None),   // DIO1
        Input::new(p.GPIO13, Pull::None),   // BUSY
        None,
        None,
    )
    .unwrap();

    let mut lora = LoRa::new(
        Sx126x::new(spi, iv, Config {
            chip: Sx1262,
            tcxo_ctrl: Some(TcxoCtrlVoltage::Ctrl1V7),
            use_dcdc: true,
            rx_boost: false,
        }),
        false,
        Delay,
    )
    .await
    .expect("LoRa init failed");

    // SF12 / BW125 / CR4-8 — maximum link budget, ~2.793 s air-time per packet
    let mdltn = lora
        .create_modulation_params(
            SpreadingFactor::_12,
            Bandwidth::_125KHz,
            CodingRate::_4_8,
            LORA_FREQUENCY_HZ,
        )
        .unwrap();

    let mut tx_params = lora
        .create_tx_packet_params(8, false, true, false, &mdltn)
        .unwrap();
    let rx_params = lora
        .create_rx_packet_params(8, false, 1, true, false, &mdltn)
        .unwrap();

    println!("Alpha ready — 915 MHz SF12 BW125 CR4/8");

    let payload = [0x01u8]; // minimum 1-byte packet
    let mut rx_buf = [0u8; 1];
    let mut seq: u32 = 0;

    loop {
        // ── TRANSMIT ─────────────────────────────────────────────────────
        // Pulse Ch1 immediately before TX — this edge is the ToF start reference
        pulse(&mut tx_pin);
        lora.prepare_for_tx(&mdltn, &mut tx_params, 14, &payload)
            .await
            .unwrap();
        lora.tx().await.unwrap();

        // ── RECEIVE — wait for Beta's reply ──────────────────────────────
        // Single shot: 255 symbols × 32.768 ms @ SF12/BW125 ≈ 8.36 s timeout
        // RTT is ~5.6 s minimum, so this gives ~2.8 s margin
        lora.prepare_for_rx(RxMode::Single(255), &mdltn, &rx_params)
            .await
            .unwrap();

        match lora.rx(&rx_params, &mut rx_buf).await {
            Ok((_, status)) => {
                // Pulse Ch2 immediately on reply received — RTT end reference
                pulse(&mut rx_pin);
                // Logging after the time-critical pulse — UART must not precede it
                println!(
                    "#{} — reply received | RSSI {} dBm | SNR {} dB",
                    seq, status.rssi, status.snr
                );
            }
            Err(_) => {
                println!("#{} — RX timeout / error (no reply from Beta)", seq);
            }
        }

        seq = seq.wrapping_add(1);

        // 2 s inter-packet gap — total cycle ≥ 7.6 s
        Timer::after(Duration::from_secs(2)).await;
    }
}
