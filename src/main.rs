// Alpha — LoRa ToF transmitter
// GPIO2: pulses before TX (oscilloscope Ch1)
// GPIO5: pulses on RX reply received (oscilloscope Ch2)
// cargo run

#![no_std]
#![no_main]

mod app_desc;

use core::fmt::Write;
use embassy_executor::Spawner;
use embassy_time::{Delay, Duration, Timer};
use embedded_graphics::{
    mono_font::{ascii::FONT_5X8, MonoTextStyleBuilder},
    pixelcolor::BinaryColor,
    prelude::*,
    text::Text,
};
use embedded_hal_bus::spi::ExclusiveDevice;
use esp_backtrace as _;
use embedded_hal::delay::DelayNs;
use esp_hal::{
    gpio::{Input, Level, Output, Pull},
    i2c::master::{Config as I2cConfig, I2c},
    spi::master::Spi,
    timer::timg::TimerGroup,
};
use esp_println::println;
use heapless::String as HString;
use lora_phy::{
    iv::GenericSx126xInterfaceVariant,
    mod_params::{Bandwidth, CodingRate, RxMode, SpreadingFactor},
    sx126x::{Config, Sx126x, Sx1262, TcxoCtrlVoltage},
    LoRa,
};
use ssd1306::{prelude::*, size::DisplaySize64x32, I2CDisplayInterface, Ssd1306};

const LORA_FREQUENCY_HZ: u32 = 915_000_000;

// Pulse a pin high then low — oscilloscope timing marker
// 500 µs hold ensures the edge is visible at the AD3's lowest sample rates (~2.3 kS/s).
// The hold time is a fixed, consistent delay absorbed into the calibration offset.
#[inline(always)]
fn pulse(pin: &mut Output<'_>) {
    pin.set_high();
    esp_hal::delay::Delay::new().delay_us(500);
    pin.set_low();
}

#[esp_hal_embassy::main]
async fn main(_spawner: Spawner) {
    let p = esp_hal::init(esp_hal::Config::default());

    let timg0 = TimerGroup::new(p.TIMG0);
    esp_hal_embassy::init(timg0.timer0);

    // VEXT (GPIO36): powers OLED display (active low)
    let _vext = Output::new(p.GPIO36, Level::Low);
    Timer::after(Duration::from_millis(100)).await;

    // Oscilloscope trigger outputs
    let mut tx_pin = Output::new(p.GPIO2, Level::Low);  // Ch1 — TX fired
    let mut rx_pin = Output::new(p.GPIO5, Level::Low);  // Ch2 — reply received

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

    // SF12 / BW125 / CR4-8 — maximum link budget, ~926 ms air-time per 1-byte packet
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

    // SSD1306 64×32 OLED — SDA=GPIO17, SCL=GPIO18, addr=0x3C, RST=GPIO21
    let _oled_rst = {
        let mut rst = Output::new(p.GPIO21, Level::Low);
        esp_hal::delay::Delay::new().delay_ms(10);
        rst.set_high();
        esp_hal::delay::Delay::new().delay_ms(10);
        rst
    };
    let i2c = I2c::new(p.I2C0, I2cConfig::default())
        .unwrap()
        .with_sda(p.GPIO17)
        .with_scl(p.GPIO18);
    let di = I2CDisplayInterface::new(i2c);
    let mut display = Ssd1306::new(di, DisplaySize64x32, DisplayRotation::Rotate0)
        .into_buffered_graphics_mode();
    if display.init().is_err() {
        println!("OLED init failed — check SDA/SCL/RST pins or I2C address");
    }
    let text_style = MonoTextStyleBuilder::new()
        .font(&FONT_5X8)
        .text_color(BinaryColor::On)
        .build();
    display.clear(BinaryColor::Off).ok();
    Text::new("ALPHA", Point::new(0, 7), text_style).draw(&mut display).ok();
    display.flush().ok();

    println!("Alpha ready — 915 MHz SF12 BW125 CR4/8");

    let payload = [0x01u8]; // minimum 1-byte packet
    let mut rx_buf = [0u8; 1];
    let mut seq: u32 = 0;
    let mut last_rssi: i16 = 0;
    let mut last_snr: i16 = 0;

    loop {
        // ── TRANSMIT ─────────────────────────────────────────────────────
        // Pulse Ch1 immediately before TX — this edge is the ToF start reference
        pulse(&mut tx_pin);
        lora.prepare_for_tx(&mdltn, &mut tx_params, 14, &payload)
            .await
            .unwrap();
        lora.tx().await.unwrap();

        // TX complete — safe to update display (after timing-critical pulse)
        {
            let mut s: HString<16> = HString::new();
            display.clear(BinaryColor::Off).ok();
            Text::new("ALPHA", Point::new(0, 7), text_style).draw(&mut display).ok();
            Text::new("Tx", Point::new(52, 7), text_style).draw(&mut display).ok();
            write!(s, "RSSI:{}", last_rssi).ok();
            Text::new(&s, Point::new(0, 17), text_style).draw(&mut display).ok();
            s.clear();
            write!(s, "SNR:{}", last_snr).ok();
            Text::new(&s, Point::new(0, 27), text_style).draw(&mut display).ok();
            display.flush().ok();
        }

        // ── RECEIVE — wait for Beta's reply ──────────────────────────────
        // Single shot: 40 symbols × 32.768 ms @ SF12/BW125 ≈ 1.31 s timeout
        // Expected wait ~930 ms (turnaround + 926 ms packet) — ~380 ms margin
        lora.prepare_for_rx(RxMode::Single(40), &mdltn, &rx_params)
            .await
            .unwrap();

        match lora.rx(&rx_params, &mut rx_buf).await {
            Ok((_, status)) => {
                // Pulse Ch2 immediately on reply received — RTT end reference
                pulse(&mut rx_pin);
                // Logging and display after the time-critical pulse
                println!(
                    "#{} — reply received | RSSI {} dBm | SNR {} dB",
                    seq, status.rssi, status.snr
                );
                last_rssi = status.rssi;
                last_snr = status.snr;
                let mut s: HString<16> = HString::new();
                display.clear(BinaryColor::Off).ok();
                Text::new("ALPHA", Point::new(0, 7), text_style).draw(&mut display).ok();
                Text::new("Rx", Point::new(52, 7), text_style).draw(&mut display).ok();
                write!(s, "RSSI:{}", last_rssi).ok();
                Text::new(&s, Point::new(0, 17), text_style).draw(&mut display).ok();
                s.clear();
                write!(s, "SNR:{}", last_snr).ok();
                Text::new(&s, Point::new(0, 27), text_style).draw(&mut display).ok();
                display.flush().ok();
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
