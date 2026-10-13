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
    if s in ['-', 'na', 'n/a', '', 'nan']:
        return None
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('₹', '').replace('rs', '')
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def parse_date(date_str):
    """Safely parses dates."""
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()
    # Try standard parsing first
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except Exception:
        pass
    # Fallback for formats like "12 Oct '26"
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
        # Explicitly read Sheet3 to avoid confusion
        df = pd.read_excel(EXCEL_FILE, sheet_name='Sheet3')
    except Exception as e:
        print(f"❌ Error reading Excel: {e}")
        return

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]
    
    today = date.today()
    live_list = []
    past_list = []

    print(f"🚀 Processing IPOs against today's date: {today}\n")

    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name or str(name).lower() == 'nan':
            continue

        listed_date = parse_date(row.get("Listing Date"))
        issue_price = parse_num(row.get("Issue Price")) or parse_num(row.get("Issue Price High"))
        
        qib = parse_num(row.get("QIB"))
        hni = parse_num(row.get("HNI"))
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        ltp = parse_num(row.get("LTP")) or parse_num(row.get("Current Traded Price"))
        listing_open = parse_num(row.get("Listing Open"))
        gain_pct = parse_num(row.get("Gain %")) or parse_num(row.get("Current Gain"))
        
        ipo_type = str(row.get("Stock Type", "Mainboard")).strip()
        if not ipo_type or ipo_type.lower() == 'nan':
            ipo_type = "Mainboard"

        # --- STRICT CATEGORIZATION LOGIC ---
        
        # Condition 1: Is it definitely Past?
        # If we have an LTP, or if the Listing Date has passed, it is PAST.
        is_past = False
        if ltp is not None:
            is_past = True
        elif listed_date is not None and listed_date < today:
            is_past = True
            
        # Condition 2: Is it Live?
        # It is Live ONLY if it is NOT past AND has a valid future/current listing date.
        is_live = False
        if not is_past and listed_date is not None and listed_date >= today:
            is_live = True

        if is_past:
            # Calculate gain if missing
            if gain_pct is None and ltp and issue_price and issue_price > 0:
                gain_pct = round(((ltp - issue_price) / issue_price) * 100, 2)
                
            past_list.append({
                "name": name,
                "type": ipo_type,
                "listed": listed_date.isoformat() if listed_date else today.isoformat(),
                "qib": qib,
                "nii": hni,
                "retail": retail,
                "total": total,
                "offer": issue_price,
                "current": ltp,
                "pl": gain_pct
            })
            
        elif is_live:
            live_list.append({
                "name": name,
                "type": ipo_type,
                "close": listed_date.isoformat(), # Dashboard uses 'close' for Live cards
                "band_low": issue_price,
                "band_high": issue_price,
                "qib": qib,
                "nii": hni,
                "retail": retail,
                "total": total
            })
        else:
            # Skip rows that are neither clearly live nor past (e.g., no date, no price)
            pass

    # Sort lists
    live_list.sort(key=lambda x: x["close"], reverse=True)
    past_list.sort(key=lambda x: x["listed"], reverse=True)

    # Generate data.json
    output = {
        "updated": today.isoformat(),
        "live": live_list,
        "past": past_list
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Success!")
    print(f"📊 Live IPOs: {len(live_list)}")
    print(f"⏳ Past IPOs: {len(past_list)}")
    
    # Debug: Print the first 3 Live IPOs to verify
    if live_list:
        print("\n🔍 First 3 Live IPOs detected:")
        for item in live_list[:3]:
            print(f"   - {item['name']} (Closes: {item['close']})")

if __name__ == "__main__":
    main()
