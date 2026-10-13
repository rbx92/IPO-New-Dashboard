import pandas as pd
import json
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

# Today's date
TODAY = date(2026, 10, 14)
print(f"📅 Today's date: {TODAY}")
print(f"📂 Reading {EXCEL_FILE}...\n")

# Read Excel
try:
    df = pd.read_excel(EXCEL_FILE)
    print(f"✅ Successfully read {len(df)} rows from Excel")
    print(f" Columns found: {list(df.columns)}\n")
except Exception as e:
    print(f"❌ Error reading Excel: {e}")
    exit(1)

# Clean column names (remove extra spaces)
df.columns = [str(c).strip() for c in df.columns]

# Check if required columns exist
required_cols = ['Company Name', 'LTP', 'Listing Date', 'Issue Price']
for col in required_cols:
    if col not in df.columns:
        print(f"❌ Missing column: {col}")
        print(f"Available columns: {list(df.columns)}")
        exit(1)

print("🔍 Processing rows...\n")

live_list = []
past_list = []
errors = []

for index, row in df.iterrows():
    name = str(row.get('Company Name', '')).strip()
    
    # Skip empty rows or header rows
    if not name or name.lower() == 'company name' or name.lower() == 'nan':
        continue
    
    # Get raw values
    ltp_raw = row.get('LTP')
    date_raw = row.get('Listing Date')
    issue_raw = row.get('Issue Price')
    
    # Parse LTP
    ltp = None
    if pd.notna(ltp_raw):
        try:
            ltp = float(str(ltp_raw).replace(',', '').replace('x', '').strip())
        except:
            pass
    
    # Parse Issue Price
    issue_price = None
    if pd.notna(issue_raw):
        try:
            issue_price = float(str(issue_raw).replace(',', '').replace('x', '').strip())
        except:
            pass
    
    # Parse Listing Date
    listed_date = None
    if pd.notna(date_raw):
        date_str = str(date_raw).strip()
        # Handle format: "12 Oct '26" or "12 Oct 2026"
        try:
            # Try pandas first
            listed_date = pd.to_datetime(date_str, dayfirst=True).date()
        except:
            # Manual parsing for "DD Mon 'YY" format
            try:
                # Remove apostrophe
                date_str_clean = date_str.replace("'", "").replace("`", "")
                # Try different formats
                for fmt in ['%d %b %Y', '%d %b %y', '%d %B %Y', '%d %B %y']:
                    try:
                        listed_date = datetime.strptime(date_str_clean, fmt).date()
                        break
                    except:
                        continue
            except:
                pass
    
    # Get other data
    qib = row.get('QIB')
    hni = row.get('HNI')
    retail = row.get('Retail')
    total = row.get('Total')
    
    # Parse subscription values
    def parse_sub(val):
        if pd.isna(val):
            return None
        try:
            return float(str(val).replace('x', '').replace(',', '').strip())
        except:
            return None
    
    qib_val = parse_sub(qib)
    hni_val = parse_sub(hni)
    retail_val = parse_sub(retail)
    total_val = parse_sub(total)
    
    # Determine if Live or Past
    # Logic: If LTP exists AND date is in the past → Past
    # Otherwise → Live
    is_past = False
    if ltp is not None and ltp > 0:
        if listed_date is not None and listed_date < TODAY:
            is_past = True
        elif listed_date is None:
            # Has price but no date - assume past
            is_past = True
    
    # Calculate gain
    gain_pct = None
    if ltp and issue_price and issue_price > 0:
        gain_pct = round(((ltp - issue_price) / issue_price) * 100, 2)
    
    # Create IPO object
    ipo_data = {
        "name": name,
        "type": "SME",  # Default, can be updated
        "listed": listed_date.isoformat() if listed_date else TODAY.isoformat(),
        "qib": qib_val,
        "nii": hni_val,
        "retail": retail_val,
        "total": total_val,
        "offer": issue_price,
        "current": ltp,
        "pl": gain_pct
    }
    
    if is_past:
        past_list.append(ipo_data)
    else:
        ipo_data["close"] = listed_date.isoformat() if listed_date else TODAY.isoformat()
        ipo_data["band_low"] = issue_price
        ipo_data["band_high"] = issue_price
        live_list.append(ipo_data)
    
    # Print first 3 rows for debugging
    if index < 3:
        print(f"Row {index}: {name}")
        print(f"  LTP: {ltp}, Date: {listed_date}, Issue: {issue_price}")
        print(f"  → {'PAST' if is_past else 'LIVE'}\n")

# Sort lists
past_list.sort(key=lambda x: x.get('listed', ''), reverse=True)
live_list.sort(key=lambda x: x.get('close', ''), reverse=True)

# Save to JSON
output = {
    "updated": TODAY.isoformat(),
    "live": live_list,
    "past": past_list
}

with open(DATA_JSON, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n{'='*50}")
print(f"✅ DONE!")
print(f" Live IPOs: {len(live_list)}")
print(f"⚫ Past IPOs: {len(past_list)}")
print(f"{'='*50}")

# Show first 5 Live IPOs
if live_list:
    print(f"\n🔍 First {min(5, len(live_list))} Live IPOs:")
    for ipo in live_list[:5]:
        print(f"  - {ipo['name']} (Date: {ipo.get('close')}, LTP: {ipo.get('current')})")

# Show first 5 Past IPOs
if past_list:
    print(f"\n🔍 First {min(5, len(past_list))} Past IPOs:")
    for ipo in past_list[:5]:
        print(f"  - {ipo['name']} (Date: {ipo.get('listed')}, LTP: {ipo.get('current')}, Gain: {ipo.get('pl')}%)")
