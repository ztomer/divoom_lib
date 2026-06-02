from pathlib import Path

def main():
    f = Path("/Users/ztomer/Projects/divoom-control/gui/web_ui/assets/cache_gallery/group1_M00_05_06_L1ghblwtV7WETnz3AAAAAF6rkQc0306288.bin")
    content = f.read_bytes()
    print(f"Total content size: {len(content)}")
    print(f"First 15 bytes: {list(content[:15])}")
    print(f"Last 15 bytes: {list(content[-15:])}")
    
    # Try different slicing starts to find a multiple of 16
    for start in range(0, 16):
        rem = (len(content) - start) % 16
        print(f"Start offset {start}: remaining size {len(content) - start}, remainder % 16 = {rem}")

if __name__ == "__main__":
    main()
