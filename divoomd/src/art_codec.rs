//! Cloud-format codecs for art.rs: AES-CBC, magic-43/9/18/26/0xAA decoders,
//! image rescaling, SHA-1 hash. These are pure functions; split from
//! art.rs to keep both files under the 500-LOC ground rule.

use minilzo_rs::LZO;

// ── AES-CBC cloud container decoder (magic 9/18/26) ──────────────────────

/// AES-CBC decrypt with the Divoom cloud key/IV.
pub(crate) fn aes_cbc_decrypt(data: &[u8]) -> Option<Vec<u8>> {
    // Use openssl-like manual PKCS#7-unpadded AES via the `aes` + `cbc` crates, or
    // fall back to a pure-Rust implementation. Because those crates aren't listed in
    // Cargo.toml (and adding them causes a large dep tree), we implement AES-128-CBC
    // in-house using the well-tested reference algorithm here.  The key and IV are
    // public constants in the APK so there is no security concern.
    //
    // We leverage the `image` crate (already in deps) for nothing here — we do the
    // AES by hand using rijndael_tables to stay dependency-free.
    // Delegate to the actual implementation below.
    aes128cbc_decrypt_impl(data,
        b"78hrey23y28ogs89",
        b"1234567890123456")
}

// Minimal AES-128-CBC decrypt — single-purpose, no padding strip needed (we
// read only the plaintext portion we know the size of).
pub(crate) fn aes128cbc_decrypt_impl(ct: &[u8], key: &[u8; 16], iv: &[u8; 16]) -> Option<Vec<u8>> {
    // Round constants
    const RCON: [u8; 10] = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36];
    const SBOX: [u8; 256] = [
        0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
        0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
        0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
        0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
        0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
        0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
        0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
        0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
        0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
        0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
        0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
        0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
        0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
        0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
        0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
        0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
    ];
    const ISBOX: [u8; 256] = [
        0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
        0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
        0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
        0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
        0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
        0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
        0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
        0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
        0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
        0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
        0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
        0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
        0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
        0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
        0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
        0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d,
    ];

    fn xtime(a: u8) -> u8 { if a & 0x80 != 0 { (a << 1) ^ 0x1b } else { a << 1 } }
    fn gmul(mut a: u8, mut b: u8) -> u8 {
        let mut p = 0u8;
        for _ in 0..8 { if b & 1 != 0 { p ^= a; } let hi = a & 0x80; a <<= 1; if hi != 0 { a ^= 0x1b; } b >>= 1; }
        p
    }

    // Key schedule
    let mut rk = [[0u8; 4]; 44];
    for i in 0..4 { rk[i] = [key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]]; }
    for i in 4..44 {
        let mut t = rk[i-1];
        if i % 4 == 0 { t = [SBOX[t[1] as usize]^RCON[i/4-1], SBOX[t[2] as usize], SBOX[t[3] as usize], SBOX[t[0] as usize]]; }
        rk[i] = [rk[i-4][0]^t[0], rk[i-4][1]^t[1], rk[i-4][2]^t[2], rk[i-4][3]^t[3]];
    }

    if ct.is_empty() || ct.len() % 16 != 0 { return None; }
    let mut out = Vec::with_capacity(ct.len());
    let mut prev_block = *iv;
    for block in ct.chunks_exact(16) {
        // InitRoundKey (round 10)
        let mut state = [0u8; 16];
        for i in 0..16 { state[i] = block[i] ^ rk[10*4 + i/4][i%4]; }
        // 9 inverse rounds
        for r in (1..10).rev() {
            // InvShiftRows
            let t = state[13]; state[13]=state[9]; state[9]=state[5]; state[5]=state[1]; state[1]=t;
            let t = state[10]; state[10]=state[2]; state[2]=t; let t=state[14]; state[14]=state[6]; state[6]=t;
            let t = state[3]; state[3]=state[7]; state[7]=state[11]; state[11]=state[15]; state[15]=t;
            // InvSubBytes
            for b in state.iter_mut() { *b = ISBOX[*b as usize]; }
            // AddRoundKey
            for i in 0..16 { state[i] ^= rk[r*4 + i/4][i%4]; }
            // InvMixColumns
            for col in 0..4 {
                let s0=state[col*4]; let s1=state[col*4+1]; let s2=state[col*4+2]; let s3=state[col*4+3];
                state[col*4]   = gmul(s0,0x0e)^gmul(s1,0x0b)^gmul(s2,0x0d)^gmul(s3,0x09);
                state[col*4+1] = gmul(s0,0x09)^gmul(s1,0x0e)^gmul(s2,0x0b)^gmul(s3,0x0d);
                state[col*4+2] = gmul(s0,0x0d)^gmul(s1,0x09)^gmul(s2,0x0e)^gmul(s3,0x0b);
                state[col*4+3] = gmul(s0,0x0b)^gmul(s1,0x0d)^gmul(s2,0x09)^gmul(s3,0x0e);
            }
            let _ = (xtime(0),);  // silence unused fn warning
        }
        // Final round (no InvMixColumns)
        let t = state[13]; state[13]=state[9]; state[9]=state[5]; state[5]=state[1]; state[1]=t;
        let t = state[10]; state[10]=state[2]; state[2]=t; let t=state[14]; state[14]=state[6]; state[6]=t;
        let t = state[3]; state[3]=state[7]; state[7]=state[11]; state[11]=state[15]; state[15]=t;
        for b in state.iter_mut() { *b = ISBOX[*b as usize]; }
        for i in 0..16 { state[i] ^= rk[i/4][i%4]; }
        // CBC XOR with previous cipher block
        for i in 0..16 { state[i] ^= prev_block[i]; }
        out.extend_from_slice(&state);
        prev_block.copy_from_slice(block);
    }
    Some(out)
}

// ── payload decoders (ported from divoom_lib/media_decoder.py) ────────────

/// True if `d` begins with a GIF/PNG/JPG file signature.
pub(crate) fn is_image_header(d: &[u8]) -> bool {
    d.starts_with(b"GIF89a")
        || d.starts_with(b"GIF87a")
        || d.starts_with(b"\x89PNG\r\n\x1a\n")
        || d.starts_with(b"\xff\xd8")
}

/// Resolve a downloaded cloud payload to a SINGLE displayable image-file
/// (GIF/PNG/JPG) the `image` crate can decode — the image-only subset used by
/// callers that need one static file. GIF/PNG/JPG pass through; magic-43 is
/// unwrapped to its embedded image.
///
/// The full cloud/hot container handling (magic 9/18/26 → AES/LZO frames, 0xAA
/// hot → palette-delta frames, all re-encoded to an animated GIF) lives in
/// `media::resolve_to_gif`, which is what `sync_artwork` / `get_animated_preview`
/// use. This function returns None for animated containers by design.
pub(crate) fn resolve_to_image_bytes(data: &[u8]) -> Option<Vec<u8>> {
    if data.len() < 4 {
        return None;
    }
    if is_image_header(data) {
        return Some(data.to_vec());
    }
    if data[0] == 43 {
        let inner = decode_magic43(data)?;
        if is_image_header(&inner) {
            return Some(inner);
        }
    }
    None
}

/// Decode a "magic 43" cloud container — returns the embedded GIF/PNG/JPG bytes.
pub(crate) fn decode_magic43(data: &[u8]) -> Option<Vec<u8>> {
    if data.len() < 10 || data[0] != 43 { return None; }
    let text_len = u32::from_le_bytes(data[6..10].try_into().ok()?) as usize;
    let img_len_off = 10 + text_len;
    if data.len() < img_len_off + 4 { return None; }
    let img_len = u32::from_le_bytes(data[img_len_off..img_len_off+4].try_into().ok()?) as usize;
    let img_start = img_len_off + 4;
    let img_end = (img_start + img_len).min(data.len());
    Some(data[img_start..img_end].to_vec())
}

/// Decode a cloud container (magic 9 → AES-CBC 16x16 RGB) into raw 768-byte frames.
/// Returns (frames, duration_ms). Magic 18/26 (AES + LZO) are handled by
/// `decode_cloud_magic18_26` (the LZO dependency is `minilzo_rs`).
pub(crate) fn decode_cloud_magic9(data: &[u8]) -> Option<(Vec<Vec<u8>>, u32)> {
    if data.len() < 5 || data[0] != 9 { return None; }
    let total_frames = data[1] as usize;
    let speed = u16::from_be_bytes([data[2], data[3]]) as u32;
    let decrypted = aes_cbc_decrypt(&data[4..])?;
    let mut frames = Vec::new();
    for i in 0..total_frames.min(24) {
        let start = i * 768;
        let end = start + 768;
        if end > decrypted.len() { break; }
        frames.push(decrypted[start..end].to_vec());
    }
    Some((frames, if speed >= 10 { speed } else { 100 }))
}

/// Decode a magic 18/26 cloud container: header `>BHBB`
/// `[magic][total_frames][speed:2 BE][row_count][column_count]`, then AES-CBC over
/// the rest, then per frame `[size:4 BE]` + LZO1X-compressed payload that inflates
/// to `row*col*768` bytes, reassembled via `compact_tiles`. Returns
/// `(frames, width, height, duration_ms)` — each frame is `width*height*3` RGB.
/// Mirrors Python `media_decoder.decode_cloud_frames` (magic 18/26).
pub(crate) fn decode_cloud_magic18_26(data: &[u8]) -> Option<(Vec<Vec<u8>>, u32, u32, u32)> {
    if data.len() < 6 { return None; }
    let magic = data[0];
    if magic != 18 && magic != 26 { return None; }
    let total_frames = data[1] as usize;
    let speed = u16::from_be_bytes([data[2], data[3]]) as u32;
    let row_count = data[4] as usize;
    let column_count = data[5] as usize;
    if row_count == 0 || column_count == 0 { return None; }
    let decrypted = aes_cbc_decrypt(&data[6..])?;
    let uncompressed = row_count * column_count * 768;
    let lzo = LZO::init().ok()?;
    let mut frames = Vec::new();
    let mut pos = 0usize;
    for _ in 0..total_frames.min(24) {
        if pos + 4 > decrypted.len() { break; }
        let frame_size =
            u32::from_be_bytes([decrypted[pos], decrypted[pos + 1], decrypted[pos + 2], decrypted[pos + 3]]) as usize;
        pos += 4;
        if pos + frame_size > decrypted.len() { break; }
        let compressed = &decrypted[pos..pos + frame_size];
        pos += frame_size;
        let raw = lzo.decompress_safe(compressed, uncompressed).ok()?;
        frames.push(compact_tiles(&raw, row_count, column_count));
    }
    if frames.is_empty() { return None; }
    let width = (column_count * 16) as u32;
    let height = (row_count * 16) as u32;
    Some((frames, width, height, if speed >= 10 { speed } else { 100 }))
}

/// Reassemble `row_count×column_count` 16×16 tiles (concatenated in grid order,
/// each tile row-major RGB) into one `(col*16)×(row*16)` RGB frame. Pure-Python
/// `_compact_tiles` fallback ported byte-for-byte.
fn compact_tiles(data: &[u8], row_count: usize, column_count: usize) -> Vec<u8> {
    let width = column_count * 16;
    let height = row_count * 16;
    let mut out = vec![0u8; width * height * 3];
    let mut pos = 0usize;
    for grid_y in 0..row_count {
        for grid_x in 0..column_count {
            for y in 0..16 {
                for x in 0..16 {
                    if pos + 3 <= data.len() {
                        let px = grid_x * 16 + x;
                        let py = grid_y * 16 + y;
                        let oidx = (py * width + px) * 3;
                        out[oidx] = data[pos];
                        out[oidx + 1] = data[pos + 1];
                        out[oidx + 2] = data[pos + 2];
                        pos += 3;
                    }
                }
            }
        }
    }
    out
}

/// Decode a 0xAA hot-file format into raw 768-byte RGB frames.
pub(crate) fn decode_hot_file(data: &[u8]) -> Option<Vec<(Vec<u8>, u32)>> {
    if data.len() < 7 || data[0] != 0xAA { return None; }
    let mut frames: Vec<(Vec<u8>, u32)> = Vec::new();
    let mut palette: Vec<[u8; 3]> = Vec::new();
    let mut off = 0usize;
    while off + 7 <= data.len() && frames.len() < 60 {
        if data[off] != 0xAA { break; }
        let frame_len = u16::from_le_bytes([data[off+1], data[off+2]]) as usize;
        let duration = u16::from_le_bytes([data[off+3], data[off+4]]) as u32;
        let flag = data[off+5];
        let n_colors_raw = data[off+6] as usize;
        if frame_len < 7 || off + frame_len > data.len() { break; }
        let mut pos = off + 7;
        if flag == 0 {
            palette.clear();
            let n = if n_colors_raw == 0 { 256 } else { n_colors_raw };
            if pos + n * 3 > data.len() { break; }
            for _ in 0..n { palette.push([data[pos], data[pos+1], data[pos+2]]); pos += 3; }
        } else {
            if pos + n_colors_raw * 3 > data.len() { break; }
            for _ in 0..n_colors_raw { palette.push([data[pos], data[pos+1], data[pos+2]]); pos += 3; }
        }
        if palette.is_empty() { break; }
        // bits-per-pixel = (palette_len - 1).bit_length() — ceil(log2) of the index
        // space. (The old next_power_of_two().trailing_zeros() under-counted for
        // non-power-of-two palette sizes, e.g. len 3 gave 1 instead of 2.)
        let bpp = {
            let x = palette.len() - 1;
            if x == 0 { 0 } else { (usize::BITS - x.leading_zeros()) as usize }
        };
        let indices: Vec<usize> = if bpp == 0 {
            vec![0usize; 256]
        } else {
            let n_bytes = (256 * bpp + 7) / 8;
            if pos + n_bytes > data.len() { break; }
            let packed = data[pos..pos+n_bytes].iter().enumerate()
                .fold(0u128, |a, (i, &b)| a | ((b as u128) << (i * 8)));
            let mask = (1usize << bpp) - 1;
            (0..256).map(|i| (packed >> (i * bpp)) as usize & mask).collect()
        };
        if indices.iter().any(|&i| i >= palette.len()) { return None; }
        let rgb: Vec<u8> = indices.iter().flat_map(|&i| palette[i].iter().copied()).collect();
        frames.push((rgb, if duration > 0 { duration as u32 } else { 100 }));
        off += frame_len;
    }
    if frames.is_empty() { None } else { Some(frames) }
}

// ── encode one animation frame body using the C dylib ────────────────────

#[cfg(test)]
mod parity_tests {
    //! Byte-for-byte parity against the Python `media_decoder` oracle. Fixtures in
    //! `tests/cloud_fixtures/` are real cloud files + their Python-decoded frames
    //! (see the fixture generator in the round notes). These prove the Rust cloud
    //! decoders match Python BEFORE anything is pushed to a device.
    use super::*;
    use std::path::PathBuf;

    fn fpath(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/cloud_fixtures").join(name)
    }
    fn raw(name: &str) -> Vec<u8> {
        std::fs::read(fpath(name)).expect("fixture .bin")
    }
    fn oracle(name: &str) -> serde_json::Value {
        serde_json::from_slice(&std::fs::read(fpath(name)).expect("fixture .json")).expect("json")
    }
    fn unhex(s: &str) -> Vec<u8> {
        (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
    }

    #[test]
    fn magic9_matches_python_oracle() {
        let (frames, dur) = decode_cloud_magic9(&raw("magic9.bin")).expect("magic9 decode");
        let o = oracle("magic9.json");
        let exp = o["frames"].as_array().unwrap();
        assert_eq!(dur, o["dur"].as_u64().unwrap() as u32, "duration");
        assert_eq!(frames.len(), exp.len(), "frame count");
        for (i, (got, e)) in frames.iter().zip(exp).enumerate() {
            assert_eq!(*got, unhex(e.as_str().unwrap()), "magic9 frame {i} bytes differ from Python");
        }
    }

    #[test]
    fn magic18_matches_python_oracle() {
        let (frames, w, h, dur) = decode_cloud_magic18_26(&raw("magic18.bin")).expect("magic18 decode");
        let o = oracle("magic18.json");
        let size = o["size"].as_array().unwrap();
        assert_eq!(w, size[0].as_u64().unwrap() as u32, "width");
        assert_eq!(h, size[1].as_u64().unwrap() as u32, "height");
        assert_eq!(dur, o["dur"].as_u64().unwrap() as u32, "duration");
        let exp = o["frames"].as_array().unwrap();
        assert_eq!(frames.len(), exp.len(), "frame count");
        for (i, (got, e)) in frames.iter().zip(exp).enumerate() {
            assert_eq!(*got, unhex(e.as_str().unwrap()), "magic18 frame {i} bytes differ from Python");
        }
    }
}

