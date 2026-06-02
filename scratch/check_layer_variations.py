import urllib.request

def check_layer_variations():
    layer_id = "group1/M00/1C/7F/L1ghbmRHwyWEc9nrAAAAAAxqcRM5106950"
    headers = {"User-Agent": "okhttp/4.12.0"}
    
    variations = [
        f"https://fin.divoom-gz.com/{layer_id}",
        f"https://fin.divoom-gz.com/{layer_id}.png",
        f"https://fin.divoom-gz.com/{layer_id}.gif",
        f"https://fin.divoom-gz.com/{layer_id}.jpg",
    ]
    
    for url in variations:
        print(f"Probing: {url}")
        try:
            req = urllib.request.Request(url, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=3) as resp:
                print(f"  --> YES! Status: {resp.status}, Content-Type: {resp.headers.get('Content-Type')}, Content-Length: {resp.headers.get('Content-Length')}")
        except Exception as e:
            print(f"  --> Failed: {e}")

if __name__ == "__main__":
    check_layer_variations()
