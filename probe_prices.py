import json, re, urllib.request, urllib.error

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

print("PROBE ROUND 5 START")

s, b = get("https://groww.in/stocks/srit-india-ltd")
print("\nSRIT page:", s, len(b))
for v in ["139.98", "147.34", "155.09", "120.05"]:
    print(" ", v, "appears", b.count(v), "times")
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', b, re.S)
print("next_data found:", bool(m))

def walk(o, path, out):
    if isinstance(o, dict):
        for k, v in o.items():
            p = path + "/" + k
            if k in ("ltp", "lastPrice", "close", "dayChange") and isinstance(v, (int, float)):
                out.append((p, v))
            walk(v, p, out)
    elif isinstance(o, list):
        for i, v in enumerate(o[:50]):
            walk(v, path + "/" + str(i), out)

if m:
    try:
        out = []
        walk(json.loads(m.group(1)), "", out)
        for p, v in out[:12]:
            print(" ", p, "=", v)
    except Exception as e:
        print("parse failed:", e)
for mm in list(re.finditer(r'"ltp"', b))[:4]:
    print("ctx:", b[max(0, mm.start() - 120):mm.start() + 60].replace("\n", " "))

print("\n-- price API by symbol --")
for sym in ["SRIT", "VANS", "EVERESTIMS"]:
    s, b = get("https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc/" + sym)
    print(sym, s, b[:160].replace("\n", " "))

print("\n-- SME stock pages --")
for slug in ["vans-electroengineerings-ltd", "everestims-technologies-ltd", "black-opal-consultants-ltd",
             "papadmalji-agro-ltd", "green-asia-impex-ltd"]:
    s, b = get("https://groww.in/stocks/" + slug)
    print(slug, s, len(b))

print("\n-- SME IPO pages --")
for slug in ["vans-electroengineerings-ipo", "everestims-technologies-ipo"]:
    s, b = get("https://groww.in/ipo/" + slug)
    print(slug, s, len(b))
    print(" symbols:", set(re.findall(r'"(?:nseScripCode|symbol|bseScripCode)"\s*:\s*"([^"]+)"', b)))

print("\nPROBE ROUND 5 END")
