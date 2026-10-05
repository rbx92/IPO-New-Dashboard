"""Daily update of data.json for the IPO dashboard.

Step 4a: refreshes the "live" list from Groww's IPO subscription page.
If anything looks wrong it prints what it saw and stops WITHOUT touching data.json.
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


def parse_groww(html, today):
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    print("tables on page:", len(tables))
    rows_out = []
    for table in tables:
        trs = table.find_all("tr")
        if len(trs) < 2:
            continue
        head_cells = trs[0].find_all(["th", "td"])
        headers = [c.get_text(" ", strip=True).lower() for c in head_cells]
        c_name = find_col(headers, "company", "name")
        c_close = find_col(headers, "close", "end")
        c_price = find_col(headers, "price")
        c_qib = find_col(headers, "qib", "qualified")
        c_nii = find_col(headers, "nii", "hni", "non-inst", "non inst")
        c_ret = find_col(headers, "retail", "rii")
        c_tot = find_col(headers, "total")
        if c_qib is None or c_tot is None:
            print("table skipped (no QIB/Total columns), first row:", headers[:12])
            continue
        if c_name is None:
            c_name = 0
        print("subscription table found, columns:", headers)
        for tr in trs[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(x for x in (c_name, c_close, c_price, c_qib, c_nii, c_ret, c_tot) if x is not None):
                continue
            row_text = " ".join(cells)
            tm = TYPE_RE.search(row_text)
            name = TYPE_RE.sub("", cells[c_name]).strip(" -|")
            name = re.sub(r"\s+", " ", name)
            close = parse_date(cells[c_close], today) if c_close is not None else None
            if not name or close is None:
                continue
            lo, hi = parse_band(cells[c_price]) if c_price is not None else (None, None)
            rows_out.append({
                "name": name,
                "type": ("SME" if tm.group(1).lower() == "sme" else "Mainboard") if tm else None,
                "close": close.isoformat(),
                "band_low": lo,
                "band_high": hi,
                "qib": num(cells[c_qib]),
                "nii": num(cells[c_nii]) if c_nii is not None else None,
                "retail": num(cells[c_ret]) if c_ret is not None else None,
                "total": num(cells[c_tot]),
            })
        if rows_out:
            break
    return rows_out


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
    for r in rows[:3]:
        print("  sample:", r)
    if len(rows) < MIN_ROWS:
        fail("read fewer than %d IPO rows, so data.json was left unchanged" % MIN_ROWS)
    if not any(r["qib"] is not None or r["total"] is not None for r in rows):
        fail("no subscription numbers found in any row, so data.json was left unchanged")

    data["live"] = merge_live(data.get("live", []), rows, today)
    data["updated"] = today.isoformat()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print("data.json updated:", len(data["live"]), "live entries, date", data["updated"])


if __name__ == "__main__":
    main()
