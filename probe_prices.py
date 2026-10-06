"""PROBE ONLY. Tests whether NSE, BSE and Chittorgarh can be read from GitHub's servers.

It does NOT read or change data.json and never makes the workflow fail.
For each test IPO it prints what each source answered, so the log shows which one works.
"""
import re
import time

import requests
from bs4 import BeautifulSoup

TEST_IPOS = ["SRIT India", "Vans Electroengineerings", "EverestIMS Technologies"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def show(label, r):
    body = r.text.replace("\n", " ")
    print("   %s -> HTTP %s, %d bytes" % (label, r.status_code, len(r.text)))
    print("   first 400 chars:", body[:400])


def try_get(session, url, **kw):
    try:
        return session.get(url, timeout=25, **kw)
    except Exception as e:
        print("   request failed:", str(e)[:200])
        return None


def probe_nse(name):
    print("\n[NSE]", name)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
                      "Accept": "application/json, text/plain, */*",
                      "Referer": "https://www.nseindia.com/"})
    r = try_get(s, "https://www.nseindia.com/")
    if r is None:
        return
    print("   home page -> HTTP", r.status_code, "cookies:", len(s.cookies))
    time.sleep(2)
    q = name.split()[0]
    r = try_get(s, "https://www.nseindia.com/api/search/autocomplete", params={"q": q})
    if r is not None:
        show("search '%s'" % q, r)
        m = re.search(r'"symbol"\s*:\s*"([A-Z0-9&-]+)"', r.text)
        if m:
            sym = m.group(1)
            print("   symbol guess:", sym)
            time.sleep(2)
            r2 = try_get(s, "https://www.nseindia.com/api/quote-equity", params={"symbol": sym})
            if r2 is not None:
                show("quote %s" % sym, r2)


def probe_bse(name):
    print("\n[BSE]", name)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Origin": "https://www.bseindia.com",
                      "Referer": "https://www.bseindia.com/"})
    q = name.split()[0]
    r = try_get(s, "https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearch/w",
                params={"Type": "SS", "text": q})
    if r is not None:
        show("search '%s'" % q, r)
        m = re.search(r"liclick\('(\d{6})'", r.text)
        if m:
            code = m.group(1)
            print("   scrip code guess:", code)
            r2 = try_get(s, "https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w",
                         params={"Debtflag": "", "scripcode": code, "seriesid": ""})
            if r2 is not None:
                show("header %s" % code, r2)


def probe_chittorgarh(names):
    print("\n[CHITTORGARH] listing report pages")
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
    urls = ["https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/",
            "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/sme/"]
    for u in urls:
        print(" ", u)
        r = try_get(s, u)
        if r is None:
            continue
        print("   HTTP", r.status_code, "bytes", len(r.text))
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        print("   tables:", len(tables))
        for t in tables[:1]:
            head = [c.get_text(" ", strip=True) for c in t.find_all("tr")[0].find_all(["th", "td"])] if t.find_all("tr") else []
            print("   header row:", head)
        for n in names:
            key = n.split()[0].lower()
            hit = [tr for tr in soup.find_all("tr") if key in tr.get_text(" ", strip=True).lower()]
            print("   rows matching '%s': %d" % (key, len(hit)))
            for tr in hit[:2]:
                print("     ", [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])])


def main():
    print("PROBE START. Testing:", TEST_IPOS)
    for n in TEST_IPOS:
        probe_nse(n)
        probe_bse(n)
    probe_chittorgarh(TEST_IPOS)
    print("\nPROBE END")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("probe crashed but that is fine:", e)
