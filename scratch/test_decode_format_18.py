import struct
from pathlib import Path
from Crypto.Cipher import AES
from PIL import Image
import lzallright

def decrypt_aes(data):
    key = '78hrey23y28ogs89'.encode('utf-8')
    iv = '1234567890123456'.encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(data)

def decode_format_18(content):
    # Parse header
    # total_frames: 1 byte
    # speed: 2 bytes
    # row_count: 1 byte
    # column_count: 1 byte
    total_frames, speed, row_count, column_count = struct.unpack('>BHBB', content[1:6])
    print(f"Header: total_frames={total_frames}, speed={speed}, size={row_count*16}x{column_count*16}")
    
    # Decrypt remaining data
    encrypted_data = content[6:]
    decrypted_data = decrypt_aes(encrypted_data)
    
    # Extract first frame
    pos = 0
    frame_size = struct.unpack('>I', decrypted_data[pos : pos + 4])[0]
    pos += 4
    
    compressed_frame = decrypted_data[pos : pos + frame_size]
    
    # Decompress using LZO
    uncompressed_size = row_count * column_count * 256 * 3
    lzo_comp = lzallright.LZOCompressor()
    frame_data = lzo_comp.decompress(compressed_frame, uncompressed_size)
    
    # Map raw pixels to Pillow Image
    width = column_count * 16
    height = row_count * 16
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    
    p = 0
    grid_x, grid_y = 0, 0
    x, y = 0, 0
    while p + 3 <= len(frame_data):
        r, g, b = frame_data[p], frame_data[p+1], frame_data[p+2]
        real_x = x + grid_x * 16
        real_y = y + grid_y * 16
        if real_x < width and real_y < height:
            pixels[real_x, real_y] = (r, g, b)
        x += 1
        p += 3
        if (p // 3) % 16 == 0:
            x = 0
            y += 1
        if (p // 3) % 256 == 0:
            x = 0
            y = 0
            grid_x += 1
            if grid_x == column_count:
                grid_x = 0
                grid_y += 1
                
    return img

def main():
    f = Path("/Users/ztomer/Projects/divoom-control/gui/web_ui/assets/cache_gallery/group1_M00_05_06_L1ghblwtV7WETnz3AAAAAF6rkQc0306288.bin")
    if not f.exists():
        print(f"File not found: {f}")
        return
        
    content = f.read_bytes()
    img = decode_format_18(content)
    if img:
        img_resized = img.resize((128, 128), Image.Resampling.NEAREST)
        out_png = f.with_suffix(".png")
        img_resized.save(out_png)
        print(f"Successfully saved decrypted and decompressed format 18 preview to {out_png.name}")

if __name__ == "__main__":
    main()
