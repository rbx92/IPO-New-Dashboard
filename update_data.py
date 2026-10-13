import pandas as pd
import json
import re
import requests
from datetime import datetime, date
import time

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

def parse_num(val):
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '', 'nan']:
        return None
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('₹', '').replace('rs', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def parse_date(date_str):
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except Exception:
        pass
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+`?(\d{2,4})", s)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100: year += 2000
        months = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
        month = months.get(month_str, 1)
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None
    return None

def get_screener_price(name):
    """Fetches current price from Screener.in"""
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

def fetch_new_from_groww(existing_names):
    """Lightweight scraper to find new IPOs on Groww not in our Excel"""
    new_ipos = []
    try:
        r = requests.get("https://groww.in/ipo/subscription", headers=HEADERS, timeout=15)
        if r.status_code == 200:
            # Simple regex to extract company names and dates from Groww's HTML structure
            # This is a fallback; the primary source is your Excel.
            names = re.findall(r'"name":"([^"]+)"', r.text)
            for name in names:
                clean_name = re.sub(r'\s+(Ltd\.?|Limited)\s*$', '', name, flags=re.I).strip()
                if clean_name and clean_name not in existing_names:
                    new_ipos.append({"Company Name": clean_name, "Stock Type": "Mainboard"}) # Default, user can edit Excel later
    except Exception:
        pass
    return new_ipos

def main():
    print(f"📂 Reading {EXCEL_FILE}...")
    try:
        df = pd.read_excel(EXCEL_FILE)
    except FileNotFoundError:
        print(f"❌ Error: {EXCEL_FILE} not found!")
        return

    # Normalize column names (strip spaces, lowercase for easy matching)
    df.columns = [str(c).strip() for c in df.columns]
    
    # 1. Check for new IPOs on Groww
    existing_names = set(str(n).strip().lower() for n in df['Company Name'] if pd.notna(n))
    new_ipos = fetch_new_from_groww(existing_names)
    if new_ipos:
        print(f"🔍 Found {len(new_ipos)} new IPO(s) on Groww. Adding to dataset...")
        new_df = pd.DataFrame(new_ipos)
        df = pd.concat([df, new_df], ignore_index=True)

    today = date.today()
    live_list = []
    past_list = []
    updated_rows = 0

    print("🚀 Processing IPOs (fetching missing prices from Screener.in)...\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name or str(name).lower() == 'nan':
            continue

        listed_date = parse_date(row.get("Listing Date"))
        issue_price = parse_num(row.get("Issue Price")) or parse_num(row.get("Issue Price High"))
        
        qib = parse_num(row.get("QIB"))
        hni = parse_num(row.get("HNI")) # Map HNI to NII for dashboard
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        ipo_type = str(row.get("Stock Type", "Mainboard")).strip()
        if not ipo_type or ipo_type.lower() == 'nan':
            ipo_type = "Mainboard"

        # Flexible LTP column name matching
        ltp = row.get("LTP") or row.get("Current Traded Price") or row.get("Current Price")
        current_price = parse_num(ltp)
        listing_pl = parse_num(row.get("Listing Gain")) or parse_num(row.get("Listing Open")) # Fallback

        # 2. Auto-fetch missing prices from Screener.in
        if current_price is None and issue_price:
            print(f"🔍 Fetching price for: {name}...")
            current_price = get_screener_price(name)
            time.sleep(0.5) # Be polite to APIs
            if current_price:
                # Update the dataframe so the Excel file stays fresh!
                df.at[index, "LTP"] = current_price
                updated_rows += 1

        # 3. Auto-calculate Current Gain %
        gain_pct = parse_num(row.get("Gain %")) or parse_num(row.get("Current Gain"))
        if gain_pct is None and current_price and issue_price and issue_price > 0:
            gain_pct = round(((current_price - issue_price) / issue_price) * 100, 2)
            df.at[index, "Gain %"] = gain_pct
            updated_rows += 1

        # 4. Categorize as Live or Past
        is_past = (current_price is not None) and (listed_date is not None and listed_date < today)

        ipo_data = {
            "name": name,
            "type": ipo_type,
            "qib": qib,
            "nii": hni,
            "retail": retail,
            "total": total,
            "offer": issue_price,
            "current": current_price,
            "pl": gain_pct,
            "listing_pl": listing_pl
        }

        if is_past:
            ipo_data["listed"] = listed_date.isoformat() if listed_date else today.isoformat()
            past_list.append(ipo_data)
        else:
            ipo_data["close"] = listed_date.isoformat() if listed_date else today.isoformat()
            ipo_data["band_low"] = issue_price
            ipo_data["band_high"] = issue_price
            live_list.append(ipo_data)

    # 5. Save updated data back to Excel (Master file stays fresh!)
    if updated_rows > 0:
        print(f"\n💾 Saving {updated_rows} updated price(s) back to {EXCEL_FILE}...")
        df.to_excel(EXCEL_FILE, index=False)

    # 6. Generate data.json
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
