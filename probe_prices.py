import json, re, urllib.request, urllib.parse, urllib.error

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "application/json, text/html, */*", "Accept-Language": "en-IN,en;q=0.9"}

def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=25)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)[:120]

print("PROBE ROUND 4 START")

s, b = get("https://groww.in/stocks/srit-india-ltd")
print("\nSRIT stock page status:", s, "length:", len(b))
m = re.search(r'"ltp"\s*:\s*([0-9.]+)', b)
print("SRIT ltp in page:", m.group(1) if m else "not found")

names = ["SRIT India", "Vans Electroengineerings", "EverestIMS Technologies",
         "Black Opal Consultants", "Papadmalji Agro", "Green Asia Impex"]
for n in names:
    print("\n==", n)
    url = ("https://groww.in/v1/api/search/v1/entity?app=false&entity_type=stocks&page=0&q="
           + urllib.parse.quote(n) + "&size=5")
    s, b = get(url)
    print("search status:", s)
    hits = []
    try:
        hits = json.loads(b).get("data", {}).get("content", [])
    except Exception:
        print("search reply:", b[:150].replace("\n", " "))
    for c in hits[:3]:
        sym = c.get("nse_scrip_code")
        print(" hit:", c.get("title"), "| symbol:", sym, "| id:", c.get("search_id"), "| type:", c.get("entity_type"))
        if sym:
            p = ("https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc/"
                 + sym)
            s2, b2 = get(p)
            print("  price status:", s2, "|", b2[:200].replace("\n", " "))
print("\nPROBE ROUND 4 END")
