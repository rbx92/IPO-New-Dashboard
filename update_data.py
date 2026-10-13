import pandas as pd
import json
import re
import requests
import yfinance as yf
from datetime import datetime, date
import time

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, 
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

def parse_date(date_str):
    if pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    # Matches "12 Oct `26" or "12 Oct 2026"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+`?(\d{2,4})", date_str)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100:
            year += 2000
        month = MONTHS.get(month_str, 1)
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None
    return None

def parse_sub(val):
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '']:
        return None
    try:
        return round(float(s.replace('x', '').replace(',', '')), 2)
    except ValueError:
        return None

def get_screener_price(name):
    """Fetches current price from Screener.in using their search API"""
    try:
        search_url = f"https://www.screener.in/api/company/search/?q={requests.utils.quote(name)}"
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json()
            if isinstance(results, list) and len(results) > 0:
                company_id = results[0].get("id")
                if company_id:
                    page_url = f"https://www.screener.in/company/id/{company_id}/"
                    r_page = requests.get(page_url, headers=HEADERS, timeout=15)
                    if r_page.status_code == 200:
                        match = re.search(r'Current Price.*?₹\s*([\d,]+\.?\d*)', r_page.text, re.IGNORECASE | re.DOTALL)
                        if match:
                            return float(match.group(1).replace(',', ''))
    except Exception:
        pass
    return None

def get_current_price(name, issue_price):
    """Tries Screener.in first, then falls back to Yahoo Finance"""
    # 1. Try Screener (Best for Indian SMEs & Mainboard)
    price = get_screener_price(name)
    if price:
        return price
    
    # 2. Fallback to Yahoo Finance (Clean name for ticker)
    try:
        clean_name = re.sub(r'[^A-Za-z0-9]', '', name).upper()
        ticker = yf.Ticker(f"{clean_name}.NS")
        hist = ticker.history(period="5d")
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 2)
    except Exception:
        pass
    
    return None

def main():
    print(f"📂 Reading {EXCEL_FILE}...")
    try:
        df = pd.read_excel(EXCEL_FILE)
    except FileNotFoundError:
        print(f"❌ Error: {EXCEL_FILE} not found!")
        return

    # Ensure required columns exist
    for col in ["Company Name", "Listing Date", "Issue Price"]:
        if col not in df.columns:
            print(f"❌ Missing required column: {col}")
            return

    today = date.today()
    live_list = []
    past_list = []

    print("🚀 Processing IPOs (fetching missing prices & calculating gains)...\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name:
            continue

        listed_date = parse_date(row.get("Listing Date"))
        issue_price = float(row.get("Issue Price", 0)) if pd.notna(row.get("Issue Price")) else None
        
        qib = parse_sub(row.get("QIB"))
        nii = parse_sub(row.get("HNI")) # Excel uses HNI, dashboard uses NII
        retail = parse_sub(row.get("Retail"))
        total = parse_sub(row.get("Total"))
        
        # Check if user provided a Type, else default to "Mainboard"
        ipo_type = str(row.get("Type", "Mainboard")).strip() if "Type" in df.columns else "Mainboard"

        # 1. Handle Price & Gain
        ltp = row.get("LTP")
        current_price = None
        gain_pct = None

        if pd.notna(ltp) and str(ltp).strip() not in ['-', 'NA', 'N/A', '']:
            try:
                current_price = round(float(str(ltp).replace('x', '').replace(',', '')), 2)
            except ValueError:
                current_price = None

        # If LTP is missing, fetch it automatically!
        if current_price is None and issue_price:
            print(f"🔍 Fetching price for: {name}...")
            current_price = get_current_price(name, issue_price)
            time.sleep(0.5) # Be polite to APIs

        # Auto-calculate Profit Percentage
        if current_price and issue_price and issue_price > 0:
            gain_pct = round(((current_price - issue_price) / issue_price) * 100, 2)

        # 2. Categorize as Live or Past
        # If it has a current price and listing date is in the past, it's "Past"
        is_past = (current_price is not None) and (listed_date is not None and listed_date < today)

        if is_past:
            past_list.append({
                "name": name,
                "type": ipo_type,
                "listed": listed_date.isoformat() if listed_date else today.isoformat(),
                "qib": qib,
                "nii": nii,
                "retail": retail,
                "total": total,
                "offer": issue_price,
                "current": current_price,
                "pl": gain_pct
            })
            print(f"✅ {name} | Listed: {current_price} | Gain: {gain_pct}%")
        else:
            # It's Live or Upcoming
            live_list.append({
                "name": name,
                "type": ipo_type,
                "close": listed_date.isoformat() if listed_date else today.isoformat(),
                "band_low": issue_price,
                "band_high": issue_price,
                "qib": qib,
                "nii": nii,
                "retail": retail,
                "total": total
            })
            if current_price:
                print(f"⏳ {name} | Upcoming/Listing | Est. Price: {current_price}")
            else:
                print(f"⏳ {name} | Upcoming/Listing | Price: Waiting")

    # 3. Save to data.json
    output = {
        "updated": today.isoformat(),
        "live": sorted(live_list, key=lambda x: x["close"], reverse=True),
        "past": sorted(past_list, key=lambda x: x["listed"], reverse=True)
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Success! data.json updated with {len(live_list)} Live and {len(past_list)} Past IPOs.")

if __name__ == "__main__":
    main()
