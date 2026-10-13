import pandas as pd
import json
import re
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

def parse_date(date_str):
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()
    
    # 1. Try pandas native parser
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except Exception:
        pass
    
    # 2. Regex for "12 Oct '26" or "12 Oct `26" or "12 Oct 2026"
    # Note the ['`]? part to handle both apostrophe and backtick
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+['`]?(\d{2,4})", s)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100:
            year += 2000
        months = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, 
                  "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
        month = months.get(month_str, 1)
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None
    return None

def parse_num(val):
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '', 'nan']:
        return None
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('₹', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def main():
    print(f"📂 Reading {EXCEL_FILE}...")
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Sheet3')
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]
    
    today = date.today()
    live_list = []
    past_list = []
    skipped = 0

    print(f"🚀 Processing rows (Today is {today})...\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        
        # Skip empty rows or accidental header rows
        if not name or name.lower() == 'company name' or name.lower() == 'nan':
            skipped += 1
            continue

        listed_date = parse_date(row.get("Listing Date"))
        issue_price = parse_num(row.get("Issue Price"))
        ltp = parse_num(row.get("LTP"))
        
        qib = parse_num(row.get("QIB"))
        hni = parse_num(row.get("HNI"))
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        ipo_type = str(row.get("Stock Type", "Mainboard")).strip()
        if not ipo_type or ipo_type.lower() == 'nan':
            ipo_type = "Mainboard"

        # --- LOGIC ---
        # If it has an LTP, it's definitely trading (Past)
        is_past = False
        if ltp is not None and ltp > 0:
            is_past = True
        elif listed_date is not None and listed_date < today:
            is_past = True

        if is_past:
            gain_pct = None
            if ltp and issue_price and issue_price > 0:
                gain_pct = round(((ltp - issue_price) / issue_price) * 100, 2)
                
            past_list.append({
                "name": name,
                "type": ipo_type,
                "listed": listed_date.isoformat() if listed_date else today.isoformat(),
                "qib": qib, "nii": hni, "retail": retail, "total": total,
                "offer": issue_price, "current": ltp, "pl": gain_pct
            })
        else:
            live_list.append({
                "name": name,
                "type": ipo_type,
                "close": listed_date.isoformat() if listed_date else today.isoformat(),
                "band_low": issue_price, "band_high": issue_price,
                "qib": qib, "nii": hni, "retail": retail, "total": total
            })

    # Sort: Past by date (newest first), Live by date (newest first)
    past_list.sort(key=lambda x: x["listed"], reverse=True)
    live_list.sort(key=lambda x: x["close"], reverse=True)

    output = {
        "updated": today.isoformat(),
        "live": live_list,
        "past": past_list
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done!")
    print(f" Live: {len(live_list)}")
    print(f"⏳ Past: {len(past_list)}")
    print(f"⚠️ Skipped: {skipped} (headers/empty)")

if __name__ == "__main__":
    main()
