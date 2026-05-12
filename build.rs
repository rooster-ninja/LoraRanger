use std::{env, fs, path::PathBuf};

fn main() {
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());

    // Shadow esp-hal's rodata.x to ensure .rodata_desc (our app descriptor) is placed
    // first in .rodata — the bootloader reads esp_app_desc_t from the first bytes there.
    fs::write(
        out.join("rodata.x"),
        b"SECTIONS {\n\
          .rodata : ALIGN(4) {\n\
              . = ALIGN(4);\n\
              _rodata_start = ABSOLUTE(.);\n\
              *(.rodata_desc)\n\
              *(.rodata .rodata.*)\n\
              *(.srodata .srodata.*)\n\
              . = ALIGN(4);\n\
              _rodata_end = ABSOLUTE(.);\n\
          } > RODATA\n\
          .rodata.wifi : ALIGN(4) {\n\
              . = ALIGN(4);\n\
              *(.rodata_wlog_*.*)\n\
              . = ALIGN(4);\n\
          } > RODATA\n\
        }\n",
    )
    .unwrap();

    println!("cargo:rustc-link-search={}", out.display());
    println!("cargo:rustc-link-arg=-Tlinkall.x");
}
