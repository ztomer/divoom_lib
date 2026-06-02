import urllib.request
import struct

def test_layer():
    # From category_list_sample.json item 1
    file_id = "group1/M00/1E/11/eEwpPWRHwySESJoKAAAAAEnILhs8539141"
    layer_id = "group1/M00/1C/7F/L1ghbmRHwyWEc9nrAAAAAAxqcRM5106950"
    
    headers = {"User-Agent": "okhttp/4.12.0"}
    
    print(f"Downloading FileId: {file_id}")
    try:
        req = urllib.request.Request(f"https://fin.divoom-gz.com/{file_id}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f"FileId size: {len(data)} bytes, magic: {list(data[:12])}")
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
    test_layer()
