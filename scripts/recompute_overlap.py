"""
Independently recompute S&P 500 overlap metrics on verified 7,693 ticker set.
Separates raw exact match from normalized syntax match and canonical company matching.
"""

import struct
import json
import pandas as pd
import requests

# 1. Fetch full CD from Hugging Face
zip_url = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_price/full_history.zip"
cd_offset = 587923399
cd_size = 1602175
headers = {"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"}
r = requests.get(zip_url, headers=headers, allow_redirects=True, timeout=60)
data = r.content

pos = 0
entries = []
while pos < len(data):
    if data[pos:pos+4] != b"PK\x01\x02":
        break
    fname_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
    extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
    comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]
    fname = data[pos + 46 : pos + 46 + fname_len].decode("utf-8", errors="ignore")
    entries.append(fname)
    pos += 46 + fname_len + extra_len + comment_len

raw_fnspid_csvs = [f[len("full_history/"): -4] for f in entries if f.startswith("full_history/") and not f.startswith("full_history/._") and f.endswith(".csv")]
fnspid_tickers_raw = set(raw_fnspid_csvs)
fnspid_tickers_upper = set(s.upper() for s in raw_fnspid_csvs)

print(f"Verified FNSPID Market Tickers: {len(fnspid_tickers_upper)}")

# 2. Load Phase 1 Universe
universe = pd.read_parquet("data/processed/universe/sp500_universe.parquet")
all_univ_tickers = set(universe["ticker"].str.upper().unique())
active_rows = universe[universe["effective_to"].isna()]
active_univ_tickers = set(active_rows["ticker"].str.upper().unique())
historical_univ_tickers = all_univ_tickers - active_univ_tickers

# A. Raw Exact Symbol Matching
raw_total_overlap = all_univ_tickers.intersection(fnspid_tickers_upper)
raw_active_overlap = active_univ_tickers.intersection(fnspid_tickers_upper)
raw_hist_overlap = historical_univ_tickers.intersection(fnspid_tickers_upper)

print("\n--- A. RAW EXACT SYMBOL MATCHING ---")
print(f"Total Universe Symbols: {len(all_univ_tickers)}")
print(f"  Raw Total Overlap: {len(raw_total_overlap)} / {len(all_univ_tickers)} ({len(raw_total_overlap)/len(all_univ_tickers)*100:.2f}%)")
print(f"  Raw Total Missing: {len(all_univ_tickers - raw_total_overlap)} ({len(all_univ_tickers - raw_total_overlap)/len(all_univ_tickers)*100:.2f}%)")
print(f"Active Universe Symbols: {len(active_univ_tickers)}")
print(f"  Raw Active Overlap: {len(raw_active_overlap)} / {len(active_univ_tickers)} ({len(raw_active_overlap)/len(active_univ_tickers)*100:.2f}%)")
print(f"  Raw Active Missing: {len(active_univ_tickers - raw_active_overlap)} ({len(active_univ_tickers - raw_active_overlap)/len(active_univ_tickers)*100:.2f}%)")
print(f"Historical Universe Symbols: {len(historical_univ_tickers)}")
print(f"  Raw Historical Overlap: {len(raw_hist_overlap)} / {len(historical_univ_tickers)} ({len(raw_hist_overlap)/len(historical_univ_tickers)*100:.2f}%)")
print(f"  Raw Historical Missing: {len(historical_univ_tickers - raw_hist_overlap)} ({len(historical_univ_tickers - raw_hist_overlap)/len(historical_univ_tickers)*100:.2f}%)")

# B. Syntax / Dot-Notation Normalization Matching
# Check dot vs dash (e.g. BRK.B -> BRK-B or BRKB, BF.B -> BF-B or BFB)
dot_symbols = [t for t in all_univ_tickers if "." in t]
dot_matches = {}
for dt in dot_symbols:
    dash = dt.replace(".", "-")
    und = dt.replace(".", "_")
    nodot = dt.replace(".", "")
    for cand in [dash, und, nodot]:
        if cand in fnspid_tickers_upper:
            dot_matches[dt] = cand
            break

print("\n--- B. SYNTAX / DOT-NOTATION NORMALIZATION ---")
print(f"Total dot symbols in universe: {len(dot_symbols)}")
print(f"Recovered via syntax normalization: {dot_matches}")

# C. Ticker Succession & Canonical Corporate Entity Matching
# Check canonical companies: If a company has multiple intervals (e.g. FB -> META),
# does FNSPID cover at least one interval of the canonical company?
all_companies = universe["company_id"].unique()
active_companies = active_rows["company_id"].unique()

comp_coverage = {}
for cid in all_companies:
    c_tickers = universe[universe["company_id"] == cid]["ticker"].str.upper().tolist()
    covered = any(t in fnspid_tickers_upper for t in c_tickers)
    comp_coverage[cid] = covered

covered_companies = sum(1 for v in comp_coverage.values() if v)
active_comp_coverage = {cid: comp_coverage[cid] for cid in active_companies}
covered_active_companies = sum(1 for v in active_comp_coverage.values() if v)

print("\n--- C. CANONICAL COMPANY IDENTITY OVERLAP ---")
print(f"Total Canonical Companies: {len(all_companies)}")
print(f"  Companies with >=1 covered interval: {covered_companies} / {len(all_companies)} ({covered_companies/len(all_companies)*100:.2f}%)")
print(f"Active Canonical Companies: {len(active_companies)}")
print(f"  Active Companies with >=1 covered interval: {covered_active_companies} / {len(active_companies)} ({covered_active_companies/len(active_companies)*100:.2f}%)")

# Note specifically: META Platforms Inc (US_CIK_0001326801):
# FB is in FNSPID, META is NOT in FNSPID!
print("\nSpecific Ticker Succession Cases:")
fb_meta_c = universe[universe["company_id"] == "US_CIK_0001326801"]["ticker"].tolist()
print(f"  Meta Platforms Inc ({fb_meta_c}): FB in FNSPID? {'FB' in fnspid_tickers_upper}, META in FNSPID? {'META' in fnspid_tickers_upper}")
