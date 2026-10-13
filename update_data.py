import pandas as pd
import json
import re
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

def parse_num(val):
    """Safely parses numbers, removing 'x', commas, and currency symbols."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '', 'nan', 'none']:
        return None
    # Clean up common formatting characters
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('₹', '').replace('rs', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def parse_date(date_str):
    """Safely parses dates, handling Excel serial numbers and text like '12 Oct '26'."""
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()
    
    # 1. Try pandas native parser (Best for actual Excel date cells)
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except Exception:
        pass
    
    # 2. Fallback to regex for text formats like "12 Oct '26"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+`?(\d{2,4})", s)
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

def main():
    print(f"📂 Reading {EXCEL_FILE}...")
    try:
        xls = pd.ExcelFile(EXCEL_FILE)
        df = None
        
        # AUTO-DETECT CORRECT SHEET (Finds the one with "Company Name")
        for sheet in xls.sheet_names:
            temp_df = pd.read_excel(xls, sheet_name=sheet)
            # Strip hidden spaces from ALL column headers
            temp_df.columns = [str(col).strip() for col in temp_df.columns]
            if 'Company Name' in temp_df.columns:
                df = temp_df
                print(f"✅ Successfully found data in sheet: '{sheet}'")
                break
        
        if df is None:
            print("❌ Error: Could not find a sheet with a 'Company Name' column.")
            return
    except Exception as e:
        print(f"❌ Error reading Excel file: {e}")
        return

    today = date.today()
    live_list = []
    past_list = []
    skipped = 0

    print(f"🚀 Processing {len(df)} rows...\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name or name.lower() == 'nan':
            skipped += 1
            continue

        listed_date = parse_date(row.get("Listing Date"))
        issue_price = parse_num(row.get("Issue Price"))
        
        # Map Excel columns to Dashboard JSON keys
        qib = parse_num(row.get("QIB"))
        nii = parse_num(row.get("HNI"))      # Excel uses HNI, Dashboard uses NII
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        # Default to Mainboard if Type column is missing
        ipo_type = str(row.get("Type", "Mainboard")).strip() if "Type" in df.columns else "Mainboard"
        if ipo_type.lower() == 'nan': ipo_type = "Mainboard"

        # 1. Get Current Price (TRUSTS YOUR EXCEL'S LTP COLUMN)
        ltp = row.get("LTP")
        current_price = parse_num(ltp)
        
        # Calculate Profit Percentage
        gain_pct = None
        if current_price and issue_price and issue_price > 0:
            gain_pct = round(((current_price - issue_price) / issue_price) * 100, 2)

        # 2. Categorize as Live or Past
        is_past = (current_price is not None) and (listed_date is not None and listed_date < today)

        if is_past:
            past_list.append({
                "name": name,
                "type": ipo_type,
                "listed": listed_date.isoformat(),
                "qib": qib,
                "nii": nii,
                "retail": retail,
                "total": total,
                "offer": issue_price,
                "current": current_price,
                "pl": gain_pct
            })
        else:
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

    # 3. Save to data.json
    output = {
        "updated": today.isoformat(),
        "live": sorted(live_list, key=lambda x: x["close"], reverse=True),
        "past": sorted(past_list, key=lambda x: x["listed"], reverse=True)
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Success! data.json updated.")
    print(f"📊 Total Past IPOs: {len(past_list)}")
    print(f"⏳ Total Live/Upcoming: {len(live_list)}")
    if skipped > 0:
        print(f"⚠️ Skipped {skipped} empty/invalid rows.")
    
    # Print a quick sample so you can verify the data in the terminal
    if past_list:
        print("\n🔍 Sample Data Verification (First Past IPO):")
        print(json.dumps(past_list[0], indent=2))

if __name__ == "__main__":
    main()
