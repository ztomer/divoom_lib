import urllib.request

def test_item4():
    file_id = "group1/M00/1F/3C/L1ghbmSgA3uEHlw7AAAAAJYf4BM5944103"
    layer_id = "group1/M00/20/C8/eEwpPWSgA3uEXDEWAAAAAHwQG-Y4179830"
    headers = {"User-Agent": "okhttp/4.12.0"}
    
    print(f"Downloading FileId: {file_id}")
    try:
        req = urllib.request.Request(f"https://fin.divoom-gz.com/{file_id}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f"FileId size: {len(data)} bytes, magic: {list(data[:12])} / {data[:12]}")
    except Exception as e:
        print(f"Failed: {e}")
        
    print(f"\nDownloading LayerFileId: {layer_id}")
    try:
        req = urllib.request.Request(f"https://fin.divoom-gz.com/{layer_id}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f"LayerFileId size: {len(data)} bytes, magic: {list(data[:12])} / {data[:12]}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_item4()
