// ESP-IDF app descriptor required by the 2nd-stage bootloader.
// Must be the first symbol in .rodata (placed at flash app_partition + 0x20).
// Layout matches esp_app_desc_t in ESP-IDF 5.3+ (256 bytes total).

const MAGIC: u32 = 0xABCD5432;

#[repr(C)]
struct EspAppDesc {
    magic_word: u32,           // 0x00
    secure_version: u32,       // 0x04
    reserv1: [u32; 2],         // 0x08
    version: [u8; 32],         // 0x10
    project_name: [u8; 32],    // 0x30
    time: [u8; 16],            // 0x50
    date: [u8; 16],            // 0x60
    idf_ver: [u8; 32],         // 0x70
    app_elf_sha256: [u8; 32],  // 0x90
    reserv2: [u32; 18],        // 0xB0  (was [u32;20] pre-5.3, last 2 u32s became fields below)
    min_efuse_blk_rev: u16,    // 0xF8
    max_efuse_blk_rev: u16,    // 0xFA
    reserv3: u32,              // 0xFC
}                              // 0x100 = 256 bytes

const _: () = assert!(core::mem::size_of::<EspAppDesc>() == 256);

#[link_section = ".rodata_desc"]
#[used]
static APP_DESC: EspAppDesc = EspAppDesc {
    magic_word: MAGIC,
    secure_version: 0,
    reserv1: [0; 2],
    version: *b"0.1.0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0",
    project_name: *b"ping_esp32\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0",
    time: [0; 16],
    date: [0; 16],
    idf_ver: *b"v5.5.1\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0",
    app_elf_sha256: [0; 32],
    reserv2: [0; 18],
    min_efuse_blk_rev: 0,
    max_efuse_blk_rev: 0xFFFF,
    reserv3: 0,
};
