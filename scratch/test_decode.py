import struct
from pathlib import Path
from Crypto.Cipher import AES
from PIL import Image

def decrypt_aes(data):
    key = '78hrey23y28ogs89'.encode('utf-8')
    iv = '1234567890123456'.encode('utf-8')
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.decrypt(data)

def decode_format_9(content):
    # Strip first 4 bytes
    encrypted_data = content[4:]
    
    # Decrypt AES
    decrypted_data = decrypt_aes(encrypted_data)
    
    # We want the first frame (768 bytes for 16x16 raw RGB)
    if len(decrypted_data) < 768:
        return None
        
    frame_bytes = decrypted_data[:768]
    return frame_bytes

def main():
    cache_dir = Path("/Users/ztomer/Projects/divoom-control/gui/web_ui/assets/cache_gallery")
    for f in cache_dir.glob("*.bin"):
        # Let's read first byte
        content = f.read_bytes()
        if not content:
            continue
        magic = content[0]
        if magic == 9:
            print(f"Found format 9 file: {f.name} (size {len(content)} bytes)")
            frame_bytes = decode_format_9(content)
            if frame_bytes:
                img = Image.frombytes("RGB", (16, 16), bytes(frame_bytes))
                out_png = f.with_suffix(".png")
                img.save(out_png)
                print(f"  Successfully saved decoded 16x16 preview to {out_png.name}")
                break

if __name__ == "__main__":
    main()
