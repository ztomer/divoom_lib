import urllib.request

def check_avatar():
    avatar_id = "group1/M00/1D/FB/eEwpPWRE_bmEXv6FAAAAAGCeS-w9596330"
    headers = {"User-Agent": "okhttp/4.12.0"}
    
    print(f"Downloading UserHeaderId: {avatar_id}")
    try:
        req = urllib.request.Request(f"https://fin.divoom-gz.com/{avatar_id}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f"UserHeaderId size: {len(data)} bytes, magic: {list(data[:12])} / {data[:12]}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    check_avatar()
