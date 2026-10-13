import pandas as pd
import json
import re
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

today = date.today()
print(f" Today is: {today}")

# 1. Find the correct sheet (Looks for the one with 'Company Name')
xls = pd.ExcelFile(EXCEL_FILE)
df = None
for sheet in xls.sheet_names:
    temp = pd.read_excel(xls, sheet_name=sheet)
    cols = [str(c).lower().strip() for c in temp.columns]
    if 'company name' in cols:
        df = temp
        print(f"✅ Using sheet: '{sheet}'")
        break

if df is None:
    print("❌ ERROR: Could not find 'Company Name' column in any sheet!")
    exit(1)

# Normalize column names (remove spaces)
df.columns = [str(c).strip() for c in df.columns]

live_list = []
past_list = []

for index, row in df.iterrows():
    name = str(row.get("Company Name", "")).strip()
    # Skip empty rows or header rows
    if not name or name.lower() == 'nan' or name.lower() == 'company name':
        continue

    # 2. Get Raw Data (Try both possible column names for each)
    ltp_raw = row.get("LTP")
    if pd.isna(ltp_raw): ltp_raw = row.get("Current Traded Price")
    
    issue_raw = row.get("Issue Price")
    if pd.isna(issue_raw): issue_raw = row.get("Issue Price High")
    
    date_raw = row.get("Listing Date")
    type_raw = row.get("Stock Type")

    # 3. Parse Numbers safely
    def safe_num(val):
        if pd.isna(val): return None
        s = str(val).replace('x', '').replace(',', '').replace('₹', '').replace(' ', '')
        try: return float(s)
        except: return None

    ltp_val = safe_num(ltp_raw)
    issue_val = safe_num(issue_raw)

    # 4. Parse Date safely (Handles "12 Oct `26" and "12 Oct '26")
    listed_date = None
    if not pd.isna(date_raw):
        s = str(date_raw).strip().replace('`', '').replace("'", "")
        try:
            listed_date = pd.to_datetime(s, dayfirst=True).date()
        except:
            # Fallback regex
            m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})", s)
            if m:
                day, mon_str, year = int(m.group(1)), m.group(2).capitalize(), int(m.group(3))
                if year < 100: year += 2000
                months = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
                try: listed_date = date(year, months.get(mon_str, 1), day)
                except: pass

    # 5. STRICT LOGIC: Determine Live vs Past
    is_past = False
    
    # Rule A: If we have a current price, it's definitely listed (Past)
    if ltp_val is not None and ltp_val > 0:
        is_past = True
    # Rule B: If the listing date is strictly before today, it's Past
    elif listed_date is not None and listed_date < today:
        is_past = True

    # 6. Categorize
    stock_type = str(type_raw).strip() if not pd.isna(type_raw) else "SME"
    if stock_type.lower() == 'nan': stock_type = "SME"

    if is_past:
        gain_pct = None
        if ltp_val and issue_val and issue_val > 0:
            gain_pct = round(((ltp_val - issue_val) / issue_val) * 100, 2)
            
        past_list.append({
            "name": name, "type": stock_type,
            "listed": listed_date.isoformat() if listed_date else today.isoformat(),
            "qib": safe_num(row.get("QIB")), "nii": safe_num(row.get("HNI")),
            "retail": safe_num(row.get("Retail")), "total": safe_num(row.get("Total")),
            "offer": issue_val, "current": ltp_val, "pl": gain_pct
        })
    else:
        live_list.append({
            "name": name, "type": stock_type,
            "close": listed_date.isoformat() if listed_date else today.isoformat(),
            "band_low": issue_val, "band_high": issue_val,
            "qib": safe_num(row.get("QIB")), "nii": safe_num(row.get("HNI")),
            "retail": safe_num(row.get("Retail")), "total": safe_num(row.get("Total"))
        })

# 7. Save
output = {
    "updated": today.isoformat(),
    "live": sorted(live_list, key=lambda x: x["close"], reverse=True),
    "past": sorted(past_list, key=lambda x: x["listed"], reverse=True)
}

with open(DATA_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n🎉 DONE!")
print(f"🟢 Live IPOs: {len(live_list)}")
print(f"⚫ Past IPOs: {len(past_list)}")

# Debug: Print first 3 Live IPOs so we can see what's happening
if live_list:
    print("\n First 3 Live IPOs detected:")
    for item in live_list[:3]:
        print(f"   - {item['name']} (Date: {item['close']}, LTP: {item.get('current')})")
