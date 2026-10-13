import pandas as pd
import json
import re
from datetime import datetime, date

EXCEL_FILE = "IPO - Self Populated.xlsx"
DATA_JSON = "data.json"

def parse_date(date_str):
    """Parse dates in format '12 Oct `26' or '12 Oct 2026'"""
    if pd.isna(date_str):
        return None
    
    s = str(date_str).strip()
    
    # Try pandas first
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.date()
    except:
        pass
    
    # Handle format: "12 Oct `26" or "12 Oct 26"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+`?(\d{2,4})", s)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).capitalize()
        year = int(match.group(3))
        if year < 100:
            year += 2000
        
        months = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, 
                  "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
        month = months.get(month_str)
        
        if month:
            try:
                return date(year, month, day)
            except:
                pass
    
    return None

def parse_num(val):
    """Parse numbers, removing 'x', commas, etc."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ['-', 'na', 'n/a', '', 'nan']:
        return None
    s = s.replace('x', '').replace(',', '').replace(' ', '').replace('₹', '')
    try:
        return round(float(s), 2)
    except:
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
    
    print(f" Processing {len(df)} rows...\n")
    
    for index, row in df.iterrows():
        name = str(row.get("Company Name", "")).strip()
        if not name or str(name).lower() == 'nan':
            continue
        
        # Parse listing date
        listed_date = parse_date(row.get("Listing Date"))
        
        # Get LTP from Excel (THIS IS THE SOURCE OF TRUTH)
        ltp = parse_num(row.get("LTP"))
        
        # Get issue price
        issue_price = parse_num(row.get("Issue Price"))
        
        # Get subscription data
        qib = parse_num(row.get("QIB"))
        hni = parse_num(row.get("HNI"))
        retail = parse_num(row.get("Retail"))
        total = parse_num(row.get("Total"))
        
        # Determine if Live or Past
        # Logic: If LTP exists AND listing date is in the past → Past
        # Otherwise → Live
        is_past = False
        if ltp is not None and listed_date is not None and listed_date < today:
            is_past = True
        elif ltp is not None and listed_date is None:
            # Has price but no date - assume past
            is_past = True
        
        if is_past:
            # Calculate gain
            gain_pct = None
            if ltp and issue_price and issue_price > 0:
                gain_pct = round(((ltp - issue_price) / issue_price) * 100, 2)
            
            past_list.append({
                "name": name,
                "type": "Mainboard",  # Default, can be updated
                "listed": listed_date.isoformat() if listed_date else today.isoformat(),
                "qib": qib,
                "nii": hni,
                "retail": retail,
                "total": total,
                "offer": issue_price,
                "current": ltp,
                "pl": gain_pct
            })
        else:
            live_list.append({
                "name": name,
                "type": "Mainboard",
                "close": listed_date.isoformat() if listed_date else today.isoformat(),
                "band_low": issue_price,
                "band_high": issue_price,
                "qib": qib,
                "nii": hni,
                "retail": retail,
                "total": total,
                "current": ltp  # Include current price even for live
            })
    
    # Sort
    live_list.sort(key=lambda x: x.get("close", ""), reverse=True)
    past_list.sort(key=lambda x: x.get("listed", ""), reverse=True)
    
    # Save
    output = {
        "updated": today.isoformat(),
        "live": live_list,
        "past": past_list
    }
    
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Success!")
    print(f"📊 Live IPOs: {len(live_list)}")
    print(f" Past IPOs: {len(past_list)}")
    
    # Show sample
    if live_list:
        print(f"\n🔍 Sample Live IPO: {live_list[0]['name']}")
        print(f"   LTP: {live_list[0].get('current')}")
        print(f"   Close: {live_list[0].get('close')}")
    
    if past_list:
        print(f"\n Sample Past IPO: {past_list[0]['name']}")
        print(f"   LTP: {past_list[0].get('current')}")
        print(f"   Listed: {past_list[0].get('listed')}")

if __name__ == "__main__":
    main()
