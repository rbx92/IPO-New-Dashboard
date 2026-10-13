"""Daily update of data.json for the IPO dashboard.

Step 4a: refreshes the "live" list from Groww's IPO subscription page.
Step 4b: for IPOs that have closed, looks for a live market price. 
         - Mainboard: Tries Yahoo Finance first.
         - SME: Uses Screener.in (highly reliable for Indian SME stocks).
"""

import datetime
import json
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

DATA_PATH = "data.json"
GROWW_URL = "https://groww.in/ipo/subscription"
KEEP_CLOSED_DAYS = 14
MIN_ROWS = 3
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

MONTHS = {m: i+1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
)}

TYPE_RE = re.compile(r"\b(Mainboard|SME)\b", re.I)
PRICE_API = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/%s/segment/CASH/latest_prices_ohlc/%s"
IPO_PAGE = "https://groww.in/ipo/%s-ipo"
STOCK_PAGE = "https://www.screener.in/company/id/%s/" # Updated to Screener for universal fallback
SCREENER_SEARCH_API = "https://www.screener.in/api/company/search/?q=%s"

PAUSE = 0.7

RESCUE = [
    {"name": "SRIT India", "type": "Mainboard", "close": "2026-09-30", "band_low": 123.0, "band_high": 130.0, "qib": 91.84, "nii": 310.94, "retail": 56.75, "total": 121.24},
    {"name": "Black Opal Consultants", "type": "SME", "close": "2026-10-01", "band_low": 185.0, "band_high": 197.0, "qib": 4.38, "nii": 43.0, "retail": 27.2, "total": 25.4},
    {"name": "Papadmalji Agro", "type": "SME", "close": "2026-10-01", "band_low": 69.0, "band_high": 72.0, "qib": 86.85, "nii": 1.14, "retail": 1.21, "total": 2.16},
    {"name": "Vans Electroengineerings", "type": "SME", "close": "2026-10-01", "band_low": 112.0, "band_high": 118.0, "qib": 73.3, "nii": 450.33, "retail": 461.25, "total": 347.25},
]

def fail(msg):
    print("STOPPED:", msg)
    sys.exit(1)

def fetch(url):
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.text:
                return r.text
            last = "HTTP %s" % r.status_code
        except requests.RequestException as e:
            last = str(e)
        time.sleep(3 * (attempt + 1))
    fail("could not fetch %s (%s)" % (url, last))

def num(text):
    if text is None:
        return None
    t = text.strip().lower().replace("x", "").replace(",", "")
    if t in ("", "--", "-", "na", "n/a"):
        return None
    try:
        return round(float(t), 2)
    except ValueError:
        return None

def parse_date(text, today):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s*(\d{4})?", text)
    if m:
        day, mon, year = int(m.group(1)), m.group(2).lower(), m.group(3)
    else:
        m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})?", text)
        if not m:
            return None
        mon, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
    if mon not in MONTHS:
        return None
    try:
        if year:
            return datetime.date(int(year), MONTHS[mon], day)
        d = datetime.date(today.year, MONTHS[mon], day)
        if d < today - datetime.timedelta(days=180):
            d = d.replace(year=today.year + 1)
        elif d > today + datetime.timedelta(days=180):
            d = d.replace(year=today.year - 1)
        return d
    except ValueError:
        return None

def parse_band(text):
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", text or "")]
    if not nums:
        return None, None
    return min(nums), max(nums)

def find_col(headers, *keys):
    for i, h in enumerate(headers):
        if any(k in h for k in keys):
            return i
    return None

CELL_X = re.compile(r"^(\d[\d,]*\.?\d*x?|--+|-|na|n/a|nil|tba|)$")

def looks_like_data_row(cells):
    return (len(cells) >= 10
            and CELL_X.match(cells[5].strip().lower().replace(" ", "")) is not None
            and CELL_X.match(cells[9].strip().lower().replace(" ", "")) is not None
            and re.search(r"\d", cells[2]) is not None)

def build_row(cells, cols, today, type_from_row_text):
    def cell(key):
        i = cols.get(key)
        return cells[i] if i is not None and i < len(cells) else None
    name = cell("name") or ""
    if type_from_row_text:
        tm = TYPE_RE.search(" ".join(cells))
        name = TYPE_RE.sub("", name)
    else:
        tm = TYPE_RE.search(cell("type") or "")
        name = re.sub(r"\s+", " ", name).strip(" -|")
    close = parse_date(cell("close"), today) if cell("close") else None
    if not name or close is None:
        return None
    lo, hi = parse_band(cell("price"))
    return {
        "name": name,
        "type": ("SME" if tm.group(1).lower() == "sme" else "Mainboard") if tm else None,
        "close": close.isoformat(),
        "band_low": lo,
        "band_high": hi,
        "qib": num(cell("qib")),
        "nii": num(cell("nii")),
        "retail": num(cell("retail")),
        "total": num(cell("total")),
    }

def parse_groww(html, today):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    print("tables on page:", len(tables))
    for table in tables:
        trs = table.find_all("tr")
        if not trs:
            continue
        grid = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in trs]
        headers = [c.lower() for c in grid[0]]
        cols = {
            "name": find_col(headers, "company", "name"),
            "close": find_col(headers, "close", "end"),
            "price": find_col(headers, "price"),
            "qib": find_col(headers, "qib", "qualified"),
            "nii": find_col(headers, "nii", "hni", "non-inst", "non inst"),
            "retail": find_col(headers, "retail", "rii"),
            "total": find_col(headers, "total"),
        }
        rows_out = []
        if cols["qib"] is not None and cols["total"] is not None:
            print("table with header row found, columns:", headers)
            if cols["name"] is None:
                cols["name"] = 0
            for cells in grid[1:]:
                r = build_row(cells, cols, today, True)
                if r:
                    rows_out.append(r)
        elif looks_like_data_row(grid[0]):
            print("table without header row found, using Groww column order (%d rows)" % len(grid))
            cols = {"name": 0, "type": 1, "close": 2, "price": 4, "qib": 5, "nii": 6, "retail": 7, "total": 9}
            for cells in grid:
                if not looks_like_data_row(cells):
                    continue
                r = build_row(cells, cols, today, False)
                if r:
                    rows_out.append(r)
        else:
            print("table skipped, first row:", grid[0][:12])
        if rows_out:
            return rows_out
    return []

def describe(html):
    soup = BeautifulSoup(html, "html.parser")
    print("\n--- diagnostics ---")
    print("page length:", len(html))
    for i, t in enumerate(soup.find_all("table")):
        trs = t.find_all("tr")
        first = []
        if trs:
            first = [c.get_text(" ", strip=True)[:25] for c in trs[0].find_all(["th", "td"])][:12]
        print("table", i, "rows:", len(trs), "first row:", first)
    nd = soup.find("script", id="__NEXT_DATA__")
    print("__NEXT_DATA__ present:", bool(nd), "length:", len(nd.string or "") if nd else 0)
    print("--- end diagnostics ---\n")

def fetch_rendered(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("browser tool not installed, skipping browser fetch")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="en-IN")
            page.goto(url, wait_until="networkidle", timeout=60000)
            try:
                page.wait_for_selector("table", timeout=20000)
            except Exception:
                print("no table appeared in the browser within 20 seconds")
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print("browser fetch failed:", str(e)[:300])
        return None

def merge_live(old_live, new_rows, today):
    keep_after = today - datetime.timedelta(days=KEEP_CLOSED_DAYS)
    merged = {}
    for o in old_live:
        close = datetime.date.fromisoformat(o["close"])
        if close < today and close >= keep_after:
            merged[o["name"].lower()] = o
    for n in new_rows:
        close = datetime.date.fromisoformat(n["close"])
        if close < keep_after:
            continue
        old = merged.get(n["name"].lower())
        row = dict(n)
        if old:
            for k in ("type", "band_low", "band_high", "qib", "nii", "retail", "total"):
                if row.get(k) is None and old.get(k) is not None:
                    row[k] = old[k]
        merged[n["name"].lower()] = row
    return sorted(merged.values(), key=lambda r: (r["close"], r["name"]))

# ---------------------------------------------------------------------------
# NEW: SCREENER.IN INTEGRATION FOR SME (AND FALLBACK) PRICING
# ---------------------------------------------------------------------------

def get_screener_price(company_name):
    """Fetches current price from Screener.in using their search API + company page."""
    try:
        # Step 1: Search for the company to get its ID
        search_url = SCREENER_SEARCH_API % requests.utils.quote(company_name)
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json()
            if isinstance(results, list) and len(results) > 0:
                company_id = results[0].get("id")
                if company_id:
                    # Step 2: Fetch the company page using the ID
                    page_url = STOCK_PAGE % company_id
                    r_page = requests.get(page_url, headers=HEADERS, timeout=15)
                    if r_page.status_code == 200:
                        soup = BeautifulSoup(r_page.text, 'html.parser')
                        for li in soup.find_all('li'):
                            text = li.get_text(separator=' ', strip=True)
                            if 'Current Price' in text:
                                match = re.search(r'₹\s*([\d,]+\.?\d*)', text)
                                if match:
                                    price_str = match.group(1).replace(',', '')
                                    return float(price_str), "Screener.in"
        return None, "Screener search failed"
    except Exception as e:
        return None, str(e)

def name_key(s):
    s = re.sub(r"\s+(Ltd\.?|Limited)\s*$", "", str(s), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())

def slug_of(name):
    s = re.sub(r"\s+(Ltd\.?|Limited)\s*$", "", name, flags=re.I)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s

def quiet_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None

def next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None

def valid_quote(q):
    if not isinstance(q, dict):
        return None
    ltp, t = q.get("ltp"), q.get("lastTradeTime")
    if isinstance(ltp, (int, float)) and ltp > 0 and isinstance(t, (int, float)) and t > 0:
        return round(float(ltp), 2)
    return None

def ipo_info(name, today):
    out = {"nse": None, "bse": None, "listed": None}
    r = quiet_get(IPO_PAGE % slug_of(name))
    if not r:
        return out
    html = r.text
    vals = re.findall(r'"(?:nseScripCode|symbol|bseScripCode)"\s*:\s*"([^"]+)"', html)
    for v in vals:
        if v.isdigit() and 5 <= len(v) <= 7 and not out["bse"]:
            out["bse"] = v
        elif re.match(r"^[A-Z][A-Z0-9&-]{1,19}$", v) and not out["nse"]:
            out["nse"] = v
    for key in ("listingDate", "listing_date", "listDate"):
        m = re.search(r'"%s"\s*:\s*"([^"]+)"' % key, html)
        if m:
            v = m.group(1)
            try:
                out["listed"] = datetime.date.fromisoformat(v[:10])
            except ValueError:
                out["listed"] = parse_date(v, today)
            if out["listed"]:
                break
    return out

def price_for(name, nse, bse, ipo_type):
    """Returns (price, how) or (None, reason). 
    Priority: Yahoo Finance (Mainboard) -> Screener.in (SME/Fallback)"""
    
    # 1. Try Yahoo Finance first (Best for Mainboard)
    if ipo_type.lower() != 'sme' and nse:
        try:
            import yfinance as yf
            stock = yf.Ticker(f"{nse}.NS")
            hist = stock.history(period="5d")
            if not hist.empty:
                price = round(float(hist['Close'].iloc[-1]), 2)
                return price, f"Yahoo Finance ({nse})"
        except Exception:
            pass # Fall through to Screener

    # 2. Fallback: Use Screener.in (Highly reliable for SMEs and Indian stocks)
    price, method = get_screener_price(name)
    if price:
        return price, method

    return None, "No price found on Yahoo or Screener"

def add_rescued(data):
    have = {name_key(x["name"]) for x in data.get("live", [])}
    have |= {name_key(p["name"]) for p in data.get("past", [])}
    for r in RESCUE:
        if name_key(r["name"]) not in have:
            data["live"].append(dict(r))
            print(" put back for pricing:", r["name"])

def update_prices(data, today):
    past = data.setdefault("past", [])
    have = {name_key(p["name"]) for p in past}
    added = 0
    for l in data.get("live", []):
        if datetime.date.fromisoformat(l["close"]) >= today:
            continue
        if name_key(l["name"]) in have:
            continue
        if l.get("qib") is None and l.get("total") is None:
            print(" skip (no subscription figures):", l["name"])
            continue
        offer = l.get("band_high")
        if not offer:
            print(" skip (no band price):", l["name"])
            continue
        
        info = ipo_info(l["name"], today)
        time.sleep(PAUSE)
        
        # NEW: Pass ipo_type to price_for to optimize fetching
        price, how = price_for(l["name"], info["nse"], info["bse"], l.get("type", "Mainboard"))
        
        if price is None:
            print(" no price yet:", l["name"], "| symbol", info["nse"], "| bse", info["bse"])
            continue
            
        listed = info["listed"] or today
        past.append({
            "name": l["name"], "type": l.get("type"),
            "qib": l.get("qib"), "nii": l.get("nii"), "retail": l.get("retail"),
            "total": l.get("total"),
            "offer": offer, "current": price,
            "pl": round((price - offer) / offer * 100, 2),
            "listed": listed.isoformat(),
            "symbol": info["nse"], "bse": info["bse"],
        })
        have.add(name_key(l["name"]))
        added += 1
        print(" PRICED:", l["name"], "| issue", offer, "| now", price, "| listed", listed.isoformat(), "| via", how)
        
    refreshed = 0
    for p in past:
        if not (p.get("symbol") or p.get("bse")) or not p.get("offer"):
            continue
        price, how = price_for(p["name"], p.get("symbol"), p.get("bse"), p.get("type", "Mainboard"))
        if price is None:
            print(" refresh failed, kept old price:", p["name"])
            continue
        p["current"] = price
        p["pl"] = round((price - p["offer"]) / p["offer"] * 100, 2)
        refreshed += 1
    print("price step done: %d added to past, %d refreshed" % (added, refreshed))

def main():
    today = datetime.datetime.now(IST).date()
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    
    html = fetch(GROWW_URL)
    rows = parse_groww(html, today)
    print("rows read from the plain page:", len(rows))
    
    if len(rows) < MIN_ROWS:
        describe(html)
        print("the plain page had no usable table, trying a real browser")
        rendered = fetch_rendered(GROWW_URL)
        if rendered:
            rows = parse_groww(rendered, today)
            print("rows read from the browser page:", len(rows))
        if len(rows) < MIN_ROWS:
            describe(rendered)
        for r in rows:
            print(" row:", r["name"], "|", r["type"], "|", r["close"], "| QIB", r["qib"], "| Total", r["total"])
        if len(rows) < MIN_ROWS:
            fail("read fewer than %d IPO rows, so data.json was left unchanged" % MIN_ROWS)
        if not any(r["qib"] is not None or r["total"] is not None for r in rows):
            fail("no subscription numbers found in any row, so data.json was left unchanged")
            
    data["live"] = merge_live(data.get("live", []), rows, today)
    data["updated"] = today.isoformat()
    
    print("\n--- price step ---")
    try:
        add_rescued(data)
        update_prices(data, today)
    except Exception as e:
        print("price step failed, live list still saved:", str(e)[:300])
        
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print("data.json updated:", len(data["live"]), "live entries,", len(data.get("past", [])), "past entries, date", data["updated"])

if __name__ == "__main__":
    main()
