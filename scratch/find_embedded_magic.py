import sys
from pathlib import Path

def main():
    cache_dir = Path("/Users/ztomer/Projects/divoom-control/gui/web_ui/assets/cache_gallery")
    bin_files = list(cache_dir.glob("*.bin"))
    print(f"Scanning {len(bin_files)} cached binary files for embedded standard image formats...")
    
    for f in bin_files:
        content = f.read_bytes()
        if len(content) < 10:
            continue
            
        # Search for GIF, PNG, JPEG magic signatures
        gif_idx = content.find(b"GIF89a")
        if gif_idx == -1:
            gif_idx = content.find(b"GIF87a")
        png_idx = content.find(b"\x89PNG\r\n\x1a\n")
        jpg_idx = content.find(b"\xff\xd8")
        
        found = []
        if gif_idx != -1:
            found.append(f"GIF at offset {gif_idx}")
        if png_idx != -1:
            found.append(f"PNG at offset {png_idx}")
        if jpg_idx != -1:
            found.append(f"JPEG at offset {jpg_idx}")
            
        if found:
            print(f"File {f.name} (size {len(content)}): Found {', '.join(found)}")

if __name__ == "__main__":
    main()
