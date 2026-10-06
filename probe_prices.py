"""PROBE ONLY (round 2). Does NOT read or change data.json and never fails the workflow.

Round 1 result: NSE and BSE block GitHub's servers (HTTP 403). Chittorgarh answers but its table
is not in the plain page. This round tries:
  A) Chittorgarh listing report in a real (headless) browser
  B) NSE and BSE home pages in a real browser (just to see if a browser gets through)
  C) Groww's own search and stock page (Groww already works from GitHub)
"""
import json
import re

import requests

TEST_IPOS = ["SRIT India", "Vans Electroengineerings", "EverestIMS Technologies"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def probe_chittorgarh_browser(p):
    print("\n[A] CHITTORGARH in a browser")
    urls = ["https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/",
            "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/sme/"]
    browser = p.chromium.launch()
    for u in urls:
        print(" ", u)
        try:
            page = browser.new_page(user_agent=UA, locale="en-IN")
            resp = page.goto(u, wait_until="networkidle", timeout=60000)
            print("   HTTP", resp.status if resp else "?")
            try:
                page.wait_for_selector("table", timeout=20000)
            except Exception:
                print("   no table appeared within 20 seconds")
            tables = page.query_selector_all("table")
            print("   tables:", len(tables))
            if tables:
                rows = tables[0].query_selector_all("tr")
                if rows:
                    print("   header row:", [c.inner_text().strip() for c in rows[0].query_selector_all("th,td")])
            body = page.inner_text("body")
            for n in TEST_IPOS:
                key = n.split()[0].lower()
                lines = [ln.strip() for ln in body.split("\n") if key in ln.lower()]
                print("   lines matching '%s': %d" % (key, len(lines)))
                for ln in lines[:2]:
                    print("     ", ln[:300])
            if not tables:
                print("   page text starts:", body[:300].replace("\n", " "))
            page.close()
        except Exception as e:
            print("   browser error:", str(e)[:250])
    browser.close()


def probe_home_in_browser(p):
    print("\n[B] NSE and BSE home pages in a browser")
    browser = p.chromium.launch()
    for u in ["https://www.nseindia.com/", "https://www.bseindia.com/"]:
        try:
            page = browser.new_page(user_agent=UA, locale="en-IN")
            resp = page.goto(u, wait_until="domcontentloaded", timeout=45000)
            print("  ", u, "-> HTTP", resp.status if resp else "?", "| title:", page.title()[:80])
            page.close()
        except Exception as e:
            print("  ", u, "-> browser error:", str(e)[:200])
    browser.close()


def probe_groww(name):
    print("\n[C] GROWW", name)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
    q = name.split()[0]
    try:
        r = s.get("https://groww.in/v1/api/search/v1/entity",
                  params={"app": "false", "page": "0", "q": q, "size": "6"}, timeout=25)
    except Exception as e:
        print("   search failed:", str(e)[:200])
        return
    print("   search '%s' -> HTTP %s, %d bytes" % (q, r.status_code, len(r.text)))
    print("   first 500 chars:", r.text[:500].replace("\n", " "))
    ids = []
    try:
        data = r.json()
        for item in data.get("content", []):
            sid = item.get("search_id") or item.get("id")
            if sid:
                ids.append((item.get("title"), sid, item.get("entity_type")))
    except Exception:
        pass
    print("   results found:", ids[:4])
    for title, sid, et in ids[:2]:
        if et and et != "stocks":
            continue
        try:
            r2 = s.get("https://groww.in/stocks/" + str(sid), timeout=25)
        except Exception as e:
            print("   stock page failed:", str(e)[:200])
            continue
        print("   stock page", sid, "-> HTTP", r2.status_code, "bytes", len(r2.text))
        m = re.search(r'"ltp"\s*:\s*([0-9.]+)', r2.text)
        print("   'ltp' (last traded price) found:", m.group(1) if m else None)
        m2 = re.search(r'"(?:livePrice|close|currentPrice)"\s*:\s*\{?[^}]{0,120}', r2.text)
        print("   other price field:", m2.group(0)[:160] if m2 else None)


def main():
    print("PROBE ROUND 2 START")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            probe_chittorgarh_browser(p)
            probe_home_in_browser(p)
    except Exception as e:
        print("browser part crashed:", str(e)[:300])
    for n in TEST_IPOS:
        probe_groww(n)
    print("\nPROBE END")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("probe crashed but that is fine:", e)
