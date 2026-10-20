import json
from pathlib import Path
import pandas as pd

def parse_submissions(cik, json_path):
    with open(json_path, encoding="utf-8") as f:
        d = json.load(f)
    recent = d.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accns = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    accepts = recent.get("acceptanceDateTime", [])
    items = recent.get("items", [])
    
    records = []
    for i, form in enumerate(forms):
        if form in ("8-K", "8-K/A"):
            records.append({
                "cik": cik,
                "accession_number": accns[i] if i < len(accns) else None,
                "form": form,
                "filing_date": dates[i] if i < len(dates) else None,
                "acceptance_datetime": accepts[i] if i < len(accepts) else None,
                "items": items[i] if i < len(items) else "",
            })
    return pd.DataFrame(records)

# Check AAPL
df_aapl = parse_submissions("0000320193", "data/raw/sec/submissions/CIK0000320193.json")
df_aapl_window = df_aapl[(df_aapl["filing_date"] >= "2019-01-01") & (df_aapl["filing_date"] <= "2020-06-10")]
print(f"AAPL 8-Ks in window: {len(df_aapl_window)}")
print(df_aapl_window[["filing_date", "form", "items", "acceptance_datetime", "accession_number"]])
