import pandas as pd
import json
import re
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

def parse_date(date_str):
    """Handles formats like '08 Oct `26' or '08 Oct 2026'"""
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()
    
    # Try pandas first
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except:
        pass
    
    # Regex for DD Mon 'YY or DD Mon `YY
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+['\`]?(\d{2,4})", s)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100: year += 2000
        
        months = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, 
                  "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
        month = months.get(month_str, 1)
        try:
            return date(year, month, day)
        except:
            pass
    return None

def parse_num(val):
    """Handles '1.5x', '-', 'NA', etc."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '']:
        return None
    s = s.replace('x', '').replace(',', '').replace(' ', '')
    try:
        return round(float(s), 2)
    except:
        return None

def main():
    print(f"📂 Reading {EXCEL_FILE}...")
    try:
        # Read the first sheet that has 'Company Name'
        xls = pd.ExcelFile(EXCEL_FILE)
        df = None
        for sheet in xls.sheet_names:
            temp = pd.read_excel(xls, sheet_name=sheet)
            if 'Company Name' in temp.columns:
                df = temp
                print(f"✅ Using sheet: '{sheet}'")
                break
        if df is None:
            print("❌ Could not find 'Company Name' column!")
            return
    except Exception as e:
        print(f"❌ Error reading Excel: {e}")
        return

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]
    
    today = date.today()
    live_list = []
    past_list = []

    print(f"🚀 Processing {len(df)} rows (Today: {today})...\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name or name.lower() in ['nan', 'company name']:
            continue

        # 1. Get Data
        listed_date = parse_date(row.get("Listing Date"))
        ltp = parse_num(row.get("LTP"))
        issue_price = parse_num(row.get("Issue Price"))
        
        qib = parse_num(row.get("QIB"))
        hni = parse_num(row.get("HNI")) # Maps to NII in dashboard
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        # Default to SME if Stock Type column is missing
        stock_type = str(row.get("Stock Type", "SME")).strip()
        if stock_type.lower() in ['nan', '']: stock_type = "SME"

        # 2. Strict Logic: Live vs Past
        is_past = False
        if ltp is not None and ltp > 0:
            is_past = True
        elif listed_date is not None and listed_date < today:
            is_past = True

        # 3. Build Objects
        if is_past:
            gain_pct = None
            if ltp and issue_price and issue_price > 0:
                gain_pct = round(((ltp - issue_price) / issue_price) * 100, 2)
                
            past_list.append({
                "name": name,
                "type": stock_type,
                "listed": listed_date.isoformat() if listed_date else today.isoformat(),
                "qib": qib, "nii": hni, "retail": retail, "total": total,
                "offer": issue_price, "current": ltp, "pl": gain_pct
            })
        else:
            live_list.append({
                "name": name,
                "type": stock_type,
                "close": listed_date.isoformat() if listed_date else today.isoformat(),
                "band_low": issue_price, "band_high": issue_price,
                "qib": qib, "nii": hni, "retail": retail, "total": total
            })

    # Sort: Newest first
    past_list.sort(key=lambda x: x["listed"], reverse=True)
    live_list.sort(key=lambda x: x["close"], reverse=True)

    # 4. Save JSON
    output = {
        "updated": today.isoformat(),
        "live": live_list,
        "past": past_list
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n SUCCESS!")
    print(f"🟢 Live IPOs: {len(live_list)}")
    print(f"⚫ Past IPOs: {len(past_list)}")

if __name__ == "__main__":
    main()
