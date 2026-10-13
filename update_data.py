"""Daily update of data.json for the IPO dashboard.

Step 4a: refreshes the "live" list from Groww's IPO subscription page.
Step 4b: for IPOs that have closed, looks for a live market price on Groww. When one is found, the IPO
         moves into "past" with its issue price, current price and gain. Auto-added IPOs keep their
         price refreshed on later runs.
If anything looks wrong with the live list it prints what it saw and stops WITHOUT touching data.json.
A problem in the price step never stops the live list from being saved.
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
KEEP_CLOSED_DAYS = 10      # closed IPOs stay in "live" this long (waiting to list)
MIN_ROWS = 3               # fewer rows than this = something is wrong, do not overwrite
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
TYPE_RE = re.compile(r"\b(Mainboard|SME)\b", re.I)

PRICE_API = ("https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/%s/segment/CASH/"
             "latest_prices_ohlc/%s")
IPO_PAGE = "https://groww.in/ipo/%s-ipo"
STOCK_PAGE = "https://groww.in/stocks/%s"
PAUSE = 0.7                # seconds between price requests, to be polite to Groww


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


# A subscription cell is a number like "12.5x", or an empty-looking value ("--", "NA", blank).
# SME IPOs often have no QIB bucket, and brand-new IPOs have no figures yet, so these must count.
CELL_X = re.compile(r"^(\d[\d,]*\.?\d*x?|--+|-|na|n/a|nil|tba|)$")


def looks_like_data_row(cells):
    """Groww's table has no header row. A data row has 10 cells; cells 5 and 9 (QIB, Total) hold
    either a subscription number or an empty-looking value. A real row also has a close date."""
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
            cols = {"name": 0, "type": 1, "close": 2, "price": 4,
                    "qib": 5, "nii": 6, "retail": 7, "total": 9}
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
    """Prints what the page looks like so a failed run can be diagnosed from the log."""
    soup = BeautifulSoup(html, "html.parser")
    print("--- diagnostics ---")
    print("page length:", len(html))
    for i, t in enumerate(soup.find_all("table")):
        trs = t.find_all("tr")
        first = []
        if trs:
            first = [c.get_text(" ", strip=True)[:25] for c in trs[0].find_all(["th", "td"])][:12]
        print("table", i, "rows:", len(trs), "first row:", first)
    nd = soup.find("script", id="__NEXT_DATA__")
    print("__NEXT_DATA__ present:", bool(nd), "length:", len(nd.string or "") if nd else 0)
    low = html.lower()
    print("'qib' appears", low.count("qib"), "times")
    pos = low.find("qib")
    if pos >= 0:
        print("text around first 'qib':", html[max(0, pos - 300):pos + 500].replace("\n", " "))
    print("--- end diagnostics ---")


def fetch_rendered(url):
    """Opens the page in a real (headless) browser so scripts run, then returns the finished HTML."""
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
        if old is None:
            old = next((o for o in old_live if o["name"].lower() == n["name"].lower()), None)
        row = dict(n)
        if old:
            for k in ("type", "band_low", "band_high", "qib", "nii", "retail", "total"):
                if row.get(k) is None and old.get(k) is not None:
                    row[k] = old[k]
        merged[n["name"].lower()] = row
    return sorted(merged.values(), key=lambda r: (r["close"], r["name"]))


# ---------------------------------------------------------------------------
# Step 4b: prices for newly listed IPOs (Groww only)
# ---------------------------------------------------------------------------

def name_key(s):
    """Same idea as the dashboard: ignore 'Ltd', case and punctuation when matching names."""
    s = re.sub(r"\s+(Ltd\.?|Limited)\s*$", "", str(s), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def slug_of(name):
    s = re.sub(r"\s+(Ltd\.?|Limited)\s*$", "", name, flags=re.I)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s


def quiet_get(url):
    """Like fetch(), but returns None instead of stopping the script."""
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
    """A real traded price: positive last price and a last-trade time. Placeholders before the
    first day of trading have no trade time, so they are rejected."""
    if not isinstance(q, dict):
        return None
    ltp, t = q.get("ltp"), q.get("lastTradeTime")
    if isinstance(ltp, (int, float)) and ltp > 0 and isinstance(t, (int, float)) and t > 0:
        return round(float(ltp), 2)
    return None


def ipo_info(name, today):
    """Reads the IPO's own Groww page for its exchange symbol, BSE code and listing date."""
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


def price_for(name, nse, bse):
    """Returns (price, how) or (None, reason). Order: price service by NSE symbol, by BSE code,
    then the company's Groww stock page."""
    tries = []
    if nse:
        tries.append(("NSE", nse))
    if bse:
        tries.append(("BSE", bse))
    for exch, code in tries:
        r = quiet_get(PRICE_API % (exch, code))
        time.sleep(PAUSE)
        if r:
            try:
                p = valid_quote(r.json())
            except ValueError:
                p = None
            if p:
                return p, "price service %s %s" % (exch, code)
    s = slug_of(name)
    for slug in (s + "-ltd", s):
        r = quiet_get(STOCK_PAGE % slug)
        time.sleep(PAUSE)
        if not r:
            continue
        nd = next_data(r.text)
        lp = (((nd or {}).get("props") or {}).get("pageProps") or {}).get("livePriceData")
        if isinstance(lp, dict):
            for code in [nse, bse] + list(lp.keys()):
                if code and code in lp:
                    p = valid_quote(lp[code])
                    if p:
                        return p, "stock page %s" % slug
    return None, "no traded price found"


def update_prices(data, today):
    past = data.setdefault("past", [])
    have = {name_key(p["name"]) for p in past}
    added = 0
    for l in data.get("live", []):
        if datetime.date.fromisoformat(l["close"]) >= today:
            continue                       # still open
        if name_key(l["name"]) in have:
            continue
        if l.get("qib") is None and l.get("total") is None:
            print("  skip (no subscription figures):", l["name"])
            continue
        offer = l.get("band_high")
        if not offer:
            print("  skip (no band price):", l["name"])
            continue
        info = ipo_info(l["name"], today)
        time.sleep(PAUSE)
        price, how = price_for(l["name"], info["nse"], info["bse"])
        if price is None:
            print("  no price yet:", l["name"], "| symbol", info["nse"], "| bse", info["bse"])
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
        print("  PRICED:", l["name"], "| issue", offer, "| now", price, "| listed",
              listed.isoformat(), "| via", how)
    refreshed = 0
    for p in past:
        if not (p.get("symbol") or p.get("bse")) or not p.get("offer"):
            continue                       # only IPOs added by this script are refreshed
        price, how = price_for(p["name"], p.get("symbol"), p.get("bse"))
        if price is None:
            print("  refresh failed, kept old price:", p["name"])
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
        print("  row:", r["name"], "|", r["type"], "|", r["close"], "| QIB", r["qib"],
              "| Total", r["total"])
    if len(rows) < MIN_ROWS:
        fail("read fewer than %d IPO rows, so data.json was left unchanged" % MIN_ROWS)
    if not any(r["qib"] is not None or r["total"] is not None for r in rows):
        fail("no subscription numbers found in any row, so data.json was left unchanged")

    data["live"] = merge_live(data.get("live", []), rows, today)
    data["updated"] = today.isoformat()

    print("--- price step ---")
    try:
        update_prices(data, today)
    except Exception as e:
        print("price step failed, live list still saved:", str(e)[:300])

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print("data.json updated:", len(data["live"]), "live entries,", len(data.get("past", [])),
          "past entries, date", data["updated"])


if __name__ == "__main__":
    main()
