import sys
from pathlib import Path
import json
import pandas as pd
import requests

from src.config import get_sec_user_agent
from src.data.sec.fetcher import SECFetcher

fetcher = SECFetcher()

# 1. Fetch GOOG paginated file
goog_paged_name = "CIK0001652044-submissions-001.json"
goog_cache = fetcher.submissions_dir / goog_paged_name
if not goog_cache.exists():
    url = f"{fetcher.BASE_URL}/submissions/{goog_paged_name}"
    fetcher._throttle()
    resp = fetcher.session.get(url, timeout=30)
    resp.raise_for_status()
    with open(goog_cache, "w", encoding="utf-8") as f:
        json.dump(resp.json(), f)
    print("Fetched and cached GOOG:", goog_paged_name)
else:
    print("GOOG already cached:", goog_paged_name)

with open(goog_cache, encoding="utf-8") as f:
    d_goog = json.load(f)

forms = d_goog.get("form", [])
accns = d_goog.get("accessionNumber", [])
dates = d_goog.get("filingDate", [])
accepts = d_goog.get("acceptanceDateTime", [])
items = d_goog.get("items", [])
k8_goog = [
    {
        "cik": "0001652044",
        "accession_number": accns[i],
        "form": forms[i],
        "filing_date": dates[i],
        "acceptance_datetime": accepts[i],
        "items": items[i],
    }
    for i in range(len(forms))
    if forms[i] in ("8-K", "8-K/A") and "2019-01-01" <= dates[i] <= "2020-06-10"
]
print(f"GOOG 8-Ks in window: {len(k8_goog)}")
for k in k8_goog[:5]:
    print(" ", k)

# 2. Fetch JPM paginated files
jpm_files = [
    "CIK0000019617-submissions-044.json",
    "CIK0000019617-submissions-045.json",
    "CIK0000019617-submissions-046.json",
    "CIK0000019617-submissions-047.json",
    "CIK0000019617-submissions-048.json",
    "CIK0000019617-submissions-049.json",
    "CIK0000019617-submissions-050.json",
]
k8_jpm = []
for jf in jpm_files:
    jpm_cache = fetcher.submissions_dir / jf
    if not jpm_cache.exists():
        url = f"{fetcher.BASE_URL}/submissions/{jf}"
        fetcher._throttle()
        resp = fetcher.session.get(url, timeout=30)
        resp.raise_for_status()
        with open(jpm_cache, "w", encoding="utf-8") as f:
            json.dump(resp.json(), f)
        print("Fetched and cached JPM:", jf)
    with open(jpm_cache, encoding="utf-8") as f:
        d = json.load(f)
    forms = d.get("form", [])
    accns = d.get("accessionNumber", [])
    dates = d.get("filingDate", [])
    accepts = d.get("acceptanceDateTime", [])
    items = d.get("items", [])
    for i in range(len(forms)):
        if forms[i] in ("8-K", "8-K/A") and "2019-01-01" <= dates[i] <= "2020-06-10":
            k8_jpm.append({
                "cik": "0000019617",
                "accession_number": accns[i],
                "form": forms[i],
                "filing_date": dates[i],
                "acceptance_datetime": accepts[i],
                "items": items[i],
            })

print(f"JPM 8-Ks in window: {len(k8_jpm)}")
for k in k8_jpm[:5]:
    print(" ", k)
