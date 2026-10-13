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
    # Remove backticks or apostrophes for cleaner parsing
    s = s.replace('`', '').replace("'", "")
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except Exception:
        pass
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})", s)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100: year += 2000
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
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def main():
    print(f" Reading {EXCEL_FILE}...")
    try:
        xls = pd.ExcelFile(EXCEL_FILE)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return

    # 1. Auto-detect the correct sheet
    df = None
    target_sheet = None
    for sheet in xls.sheet_names:
        temp_df = pd.read_excel(xls, sheet_name=sheet)
        cols = [str(c).strip().lower() for c in temp_df.columns]
        if 'company name' in cols and 'listing date' in cols:
            df = temp_df
            target_sheet = sheet
            break

    if df is None:
        print("❌ Could not find a sheet with 'Company Name' and 'Listing Date'.")
        return
    
    print(f"✅ Using sheet: '{target_sheet}'")
    
    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. Auto-detect columns (handles both 'LTP' and 'Current Traded Price')
    col_map = {}
    for col in df.columns:
        lower_col = col.lower()
        if 'company name' in lower_col: col_map['name'] = col
        elif 'ltp' in lower_col or 'current traded price' in lower_col: col_map['ltp'] = col
        elif 'listing date' in lower_col: col_map['date'] = col
        elif 'issue price' in lower_col: col_map['issue'] = col
        elif 'qib' in lower_col: col_map['qib'] = col
        elif 'hni' in lower_col or 'nii' in lower_col: col_map['hni'] = col
        elif 'retail' in lower_col: col_map['retail'] = col
        elif 'total' in lower_col: col_map['total'] = col
        elif 'stock type' in lower_col or 'type' in lower_col: col_map['type'] = col

    today = date.today()
    live_list = []
    past_list = []

    print(f"🚀 Processing {len(df)} rows (Today: {today})...\n")

    for index, row in df.iterrows():
        name = str(row.get(col_map.get('name', ''), "")).strip()
        # Skip empty rows or header rows
        if not name or str(name).lower() == 'nan' or name.lower() == 'company name':
            continue

        listed_date = parse_date(row.get(col_map.get('date', ''), None))
        ltp = parse_num(row.get(col_map.get('ltp', ''), None))
        issue_price = parse_num(row.get(col_map.get('issue', ''), None))
        
        qib = parse_num(row.get(col_map.get('qib', ''), None))
        hni = parse_num(row.get(col_map.get('hni', ''), None))
        retail = parse_num(row.get(col_map.get('retail', ''), None))
        total = parse_num(row.get(col_map.get('total', ''), None))
        
        ipo_type = str(row.get(col_map.get('type', ''), "Mainboard")).strip()
        if not ipo_type or ipo_type.lower() == 'nan':
            ipo_type = "Mainboard"

        # 3. Strict Logic: If date is in the past OR it has a price, it is PAST.
        is_past = False
        if listed_date is not None and listed_date < today:
            is_past = True
        if ltp is not None and ltp > 0:
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

    # Sort lists
    past_list.sort(key=lambda x: x["listed"], reverse=True)
    live_list.sort(key=lambda x: x["close"], reverse=True)

    output = {
        "updated": today.isoformat(),
        "live": live_list,
        "past": past_list
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n Success!")
    print(f"📊 Live IPOs: {len(live_list)}")
    print(f"⏳ Past IPOs: {len(past_list)}")

if __name__ == "__main__":
    main()
