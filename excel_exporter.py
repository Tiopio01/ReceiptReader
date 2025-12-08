import pandas as pd
import re
import os
from datetime import datetime

EXCEL_FILE = "receipts_data.xlsx"

def detect_language(text_lines):
    """
    Detects if the receipt is Italian (IT) or English/American (EN) based on keyword frequency.
    Returns 'IT' or 'EN'.
    """
    it_score = 0
    en_score = 0
    
    # Common keywords found in Italian receipts
    it_keywords = ["TOTALE", "SCONTRINO", "P.IVA", "EURO", "IMPORTO", "CASSA", "SERVIZIO", "COPERTO", "VIA ", "PIAZZA "]
    # Common keywords found in English/US receipts
    en_keywords = ["TOTAL", "RECEIPT", "TAX", "TIPS", "GRATUITY", "CHANGE", "CASH", "SUBTOTAL", "AVE", "BLVD", "STREET"]
    
    for line in text_lines:
        upper = line.strip().upper()
        for kw in it_keywords:
            if kw in upper: it_score += 1
        for kw in en_keywords:
            if kw in upper: en_score += 1
            
    if en_score > it_score:
        return 'EN'
    return 'IT'

def normalize_date(date_str, lang='IT'):
    """
    Converts various date string formats into a standard dd/mm/yyyy numeric format.
    Handles common OCR errors (e.g., apostrophes instead of '20' for years).
    """
    if not date_str or date_str == "null":
        return date_str

    # Clean up the string: fix common OCR misinterpretations of dates
    clean_str = re.sub(r"'(\d{2})\b", r"20\1", date_str) # Replace '23 with 2023
    clean_str = clean_str.replace("'", "20") 
    clean_str = re.sub(r'[^\w\s]', ' ', clean_str) # Replace non-alphanumeric with space
    clean_str = re.sub(r'\s+', ' ', clean_str).strip() # Normalize spaces
    
    # List of supported date formats to try parsing
    formats = [
        "%d %m %Y", "%d %m %y", 
        "%m %d %Y", "%m %d %y",
        "%b %d %Y", "%b %d %y", 
        "%B %d %Y", "%B %d %y", 
        "%b%d %Y", "%b%d%Y"      
    ]
    
    parsed_date = None
    
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(clean_str, fmt)
            break
        except ValueError:
            continue
            
    if parsed_date:
        return parsed_date.strftime("%d/%m/%Y")
    
    # Fallback regex for dates like "Jan 12 2024" if strptime fails
    try:
        match = re.search(r'([a-zA-Z]{3})\s*(\d{1,2})\s*(\d{2,4})', clean_str)
        if match:
            m, d, y = match.groups()
            if len(y) == 2: y = "20" + y
            date_obj = datetime.strptime(f"{m} {d} {y}", "%b %d %Y")
            return date_obj.strftime("%d/%m/%Y")
    except:
        pass

    return date_str

def extract_info(text_lines, filename="unknown"):
    """
    Extracts key information: vendor, date, location, total amount, and currency 
    from a list of text lines extracted by OCR.
    Includes the source filename in the returned data structure.
    """
    data = {
        "filename": filename,
        "vendor": "null",
        "location": "null",
        "date": "null",
        "total": "null",
        "currency": "null"
    }

    if not text_lines:
        return data

    # Step 0: Detect Language to tune keywords
    lang = detect_language(text_lines)

    # Helper function to extract all valid float numbers from a string
    def get_floats(txt):
        if "%" in txt: return [] # Avoid extracting percentages as monetary values
        res = []
        matches = re.findall(num_regex, txt) 
        for m in matches:
            try:
                val = float(m.replace(',', '.'))
                # Exclude years (e.g., 2023) from being mistaken as totals
                if 1900 < val < 2100 and val.is_integer(): continue 
                res.append(val)
            except: pass
        return res

    # --- 1. Vendor Extraction ---
    # Heuristic: The vendor usually appears at the very top of the receipt.
    # We look for corporate suffixes (SPA, INC) or take the first prominent text line.
    
    if lang == 'IT':
        suffixes = ["S.P.A", "S.R.L", "SRL", "SPA", "S.N.C", "SNC"]
        skip_keywords = ["DOCUMENTO", "COMMERCIALE", "SCONTRINO", "CLIENTE", "COPIA", "RT", "CASSA", "PAGAMENTO"]
    else: 
        suffixes = ["INC", "LTD", "LLC", "CORP", "INC.", "LLC."]
        skip_keywords = ["RECEIPT", "GUEST", "CHECK", "TABLE", "SERVER", "ORDER", "WELCOME", "COPY", "MERCHANT"]

    vendor_found = False
    # Check the first 8 lines specifically for corporate suffixes
    for i, line in enumerate(text_lines[:8]):
        clean_line = line.strip()
        if len(clean_line) < 3: continue
        if any(s in clean_line.upper() for s in suffixes):
            data["vendor"] = clean_line
            vendor_found = True
            break
    
    # Fallback: If no suffix found, take the first valid line that isn't a generic keyword
    if not vendor_found:
        for line in text_lines:
            clean_line = line.strip()
            upper = clean_line.upper()
            if len(clean_line) < 3 or not any(c.isalpha() for c in clean_line): continue
            if any(k in upper for k in skip_keywords): continue
            data["vendor"] = clean_line
            break

    # --- 2. Date Extraction ---
    # Look for patterns like dd/mm/yyyy or mm-dd-yyyy depending on language.
    date_found = False
    raw_date = None
    
    if lang == 'IT':
        date_patterns = [r'\b(\d{2}\s*[/-]\s*\d{2}\s*[/-]\s*\d{2,4})\b']
    else:
        date_patterns = [
            r'\b(\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{4})',
            r'\b(\d{1,2}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{2})\b',
            r'(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{1,2})[\s\.\,\']*(\d{2,4})'
        ]

    for line in text_lines:
        for pat in date_patterns:
            match = re.search(pat, line)
            if match:
                if lang == 'EN' and 'Jan' in pat: 
                    raw_date = match.group(0)
                else:
                    raw_date = match.group(1).replace(" ", "")
                date_found = True
                break
        if date_found: break
    
    if date_found and raw_date:
        data["date"] = normalize_date(raw_date, lang)
    else:
        # Default to today if no date found, marking it in parens
        today_str = datetime.now().strftime("%d/%m/%Y")
        data["date"] = f"({today_str})"

    # --- 3. Total and Currency Extraction ---
    explicit_totals = []
    blind_totals = []
    cash_candidates = []
    currency = "null"
    
    # Detect currency symbol
    for line in text_lines:
        if "€" in line or "EUR" in line.upper():
            currency = "EUR"
            break
        if "$" in line or "USD" in line.upper():
            currency = "USD"
            break
    
    if currency == "null":
        currency = "EUR" if lang == 'IT' else "USD"

    # Define regex and keywords for total extraction
    if lang == 'IT':
        total_keywords = ["TOTALE", "IMPORTO", "PAGAMENTO", "CREDIT", "AMMOUNT"]
        cash_keywords = ["CONTANTI", "CONTANTE", "CASH", "VERSAMENTO"]
        ignore_keywords = ["SUBTOTALE", "IMPONIBILE", "RESTO"]
        num_regex = r'(\d+[\.,]\d{2})(?!["\d\.,/])' # Matches numbers like 10.99 or 10,99
    else:
        total_keywords = ["TOTAL", "BALANCE", "AMOUNT", "DUE", "VISA", "CHARGE", "BILL", "TOTA"]
        cash_keywords = ["CASH", "TENDER", "PAID"]
        ignore_keywords = ["SUBTOTAL", "SUB TOTAL", "TAX", "CHANGE", "TIP", "GRATUITY"]
        num_regex = r'[\$]?\s*(\d+\.\d{2})(?!["\d\.,/])' # Matches $10.99 or 10.99

    # Strategy A: Explicit Keyword Search
    # Look for the word "TOTAL" and check numbers on that line or immediately following lines.
    for i, line in enumerate(text_lines):
        upper = line.strip().upper()
        vals = get_floats(line)
        
        # If line contains "CASH", store it separately as a fallback (often the total is paid in cash)
        if any(kw in upper for kw in cash_keywords):
            cash_candidates.extend(vals)
            if i + 1 < len(text_lines):
                cash_candidates.extend(get_floats(text_lines[i+1]))
            continue 
            
        if any(ik in upper for ik in ignore_keywords):
            continue

        if any(kw in upper for kw in total_keywords):
            # Search current line and next 4 lines for the total amount
            for offset in range(5):
                if i + offset < len(text_lines):
                    explicit_totals.extend(get_floats(text_lines[i+offset]))

    # Strategy B: Scan Last 15 lines (Blind Search)
    # Totals are usually at the bottom. We scan the last part of the receipt for any valid numbers.
    for line in text_lines[-15:]:
        upper = line.strip().upper()
        vals = get_floats(line)
        if not vals: continue

        if any(kw in upper for kw in cash_keywords):
            cash_candidates.extend(vals)
        elif any(ik in upper for ik in ignore_keywords):
            continue
        else:
            blind_totals.extend(vals)
    
    # Final Logic to determine the best candidate for "Total"
    final_total_val = None
    max_cash = max(cash_candidates) if cash_candidates else None
    
    if explicit_totals:
        # Highest confidence: Number found near "TOTAL" keyword
        final_total_val = max(explicit_totals)
    elif blind_totals:
        # Secondary confidence: Largest number at the bottom, but capped by Cash amount if present
        # (Total shouldn't be larger than Cash tendered)
        if max_cash is not None:
            valid_blind_candidates = [t for t in blind_totals if t <= max_cash + 0.01]
            if valid_blind_candidates:
                final_total_val = max(valid_blind_candidates)
            elif blind_totals:
                final_total_val = max(blind_totals)
            else:
                final_total_val = max_cash
        else:
            final_total_val = max(blind_totals)
    elif max_cash is not None:
        final_total_val = max_cash
    
    if final_total_val is not None and final_total_val > 0:
        data["total"] = f"{final_total_val:.2f}"
    else:
        data["total"] = "null"
    
    data["currency"] = currency

    # --- 4. Location Extraction ---
    # Heuristic: Score lines based on address keywords (VIA, ST, AVE) and ZIP/Postal codes.
    if lang == 'IT':
        addr_keywords = ["VIA ", "VIALE ", "PIAZZA ", "CORSO ", "C.SO ", "VICOLO ", "LARGO ", "STRADA ", "P.ZZA ", "V. "]
        cap_pattern = r'\b\d{5}\b' # Italian CAP (5 digits)
        prov_pattern = r'\s\(?([A-Z]{2})\)?$' # Province code (e.g., (MI))
    else:
        addr_keywords = [" AVE", " ST", " BLVD", " BL VD", " RD", " DRIVE", " LANE", " HIGHWAY", " PKWY", " WAY"]
        cap_pattern = r'\b(?:[A-Z]{2}\s*)?\d{5}\b' # US Zip
        prov_pattern = r'\b[A-Z]{2}\s+\d{5}' # State + Zip

    scored_lines = []
    for i, line in enumerate(text_lines):
        clean = line.strip()
        upper = clean.upper()
        
        # Skip lines that look like dates
        is_date_line = False
        for pat in date_patterns:
            if re.search(pat, line):
                is_date_line = True
                break
        if is_date_line: continue

        score = 0
        if any(k in upper for k in addr_keywords): score += 5
        if re.search(cap_pattern, clean): score += 6
        if re.search(prov_pattern, clean): score += 4
        
        # Penalize lines containing phone/tax info or headers
        bad_words = ["TEL", "FAX", "TAX", "VAT", "ORDER", "TABLE", "GUEST", "ID", "OP:", "CASSA:", "IBAN", "N.CARTA", "CARD", "ACCT"]
        if any(bw in upper for bw in bad_words): score -= 20
        
        if score > 0:
            scored_lines.append({'index': i, 'text': clean, 'score': score})

    # Merge adjacent high-scoring lines (e.g., Street Name + City/Zip)
    final_candidates = []
    if scored_lines:
        scored_lines.sort(key=lambda x: x['index'])
        i = 0
        while i < len(scored_lines):
            curr = scored_lines[i]
            merged = False
            if i + 1 < len(scored_lines):
                next_l = scored_lines[i+1]
                if next_l['index'] == curr['index'] + 1:
                    combined_text = f"{curr['text']} {next_l['text']}"
                    combined_score = curr['score'] + next_l['score'] + 5
                    final_candidates.append({'text': combined_text, 'score': combined_score})
                    i += 2
                    merged = True
            if not merged:
                final_candidates.append(curr)
                i += 1
                
    if final_candidates:
        best = max(final_candidates, key=lambda x: x['score'])
        data["location"] = best['text']

    return data

def save_all_to_excel(data_list, filename="receipts_data.xlsx"):
    """
    Saves a list of receipt data dictionaries to an Excel file.
    Overwrites any existing file to ensure a clean state for the current session.
    Also calculates and appends summary rows with totals per currency at the bottom of the sheet.
    """
    if not data_list:
        return

    df = pd.DataFrame(data_list)
    
    # --- Calculate Totals per Currency ---
    try:
        # Convert total to numeric, coercing errors to NaN (then 0) for calculation
        df['total_numeric'] = pd.to_numeric(df['total'], errors='coerce').fillna(0)
        
        # Group by currency to get sums
        currency_sums = df.groupby('currency')['total_numeric'].sum()
        
        # Drop the temporary numeric column for the final output
        df = df.drop(columns=['total_numeric'])
        
        # Add an empty spacer row for visual separation
        empty_row = pd.DataFrame([{col: "" for col in df.columns}])
        df = pd.concat([df, empty_row], ignore_index=True)
        
        # Add summary rows (e.g., "TOTALE EUR: 50.00")
        summary_rows = []
        for curr, total_val in currency_sums.items():
            if curr == "null": continue # Skip null currencies in summary
            
            row = {
                "filename": "",
                "vendor": f"TOTALE {curr}",
                "location": "",
                "date": "",
                "total": f"{total_val:.2f}",
                "currency": curr
            }
            summary_rows.append(row)
            
        if summary_rows:
            df = pd.concat([df, pd.DataFrame(summary_rows)], ignore_index=True)
            
    except Exception as e:
        print(f"⚠️ Errore nel calcolo dei totali riepilogativi: {e}")

    try:
        # Write to Excel (Overwrite mode)
        df.to_excel(filename, index=False)
        print(f"✅ Tutti i dati ({len(data_list)} scontrini + riepilogo) salvati in {filename}")
    except Exception as e:
        print(f"❌ Errore nel salvataggio Excel: {e}")
        # Fallback to CSV if Excel saving fails (e.g., missing libraries)
        csv_filename = filename.replace(".xlsx", ".csv")
        df.to_csv(csv_filename, index=False)
        print(f"✅ Dati salvati in {csv_filename} (fallback CSV)")

def save_to_excel(data, filename="receipts_data.xlsx"):
    """
    Wrapper to save a single data item.
    """
    save_all_to_excel([data], filename)