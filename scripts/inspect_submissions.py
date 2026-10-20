import json
import pandas as pd

for cik in ['0000320193', '0000019617', '0000789019', '0000816284', '0001326801']:
    p = f'data/raw/sec/submissions/CIK{cik}.json'
    with open(p, encoding='utf-8') as f:
        d = json.load(f)
    recent = d.get('filings', {}).get('recent', {})
    print(f"=== CIK: {cik}, name: {d.get('name')}, tickers: {d.get('tickers')} ===")
    print(f"Recent keys: {list(recent.keys())}")
    forms = recent.get('form', [])
    k8_indices = [i for i, f in enumerate(forms) if f in ('8-K', '8-K/A')]
    print(f"Total filings in recent: {len(forms)}, 8-K count: {len(k8_indices)}")
    if k8_indices:
        sample = {k: recent[k][k8_indices[0]] for k in recent}
        print(f"Sample 8-K: {sample}")
        items_samples = [recent['items'][i] for i in k8_indices[:5] if 'items' in recent]
        print(f"First 5 8-K items: {items_samples}")
        dates = [recent['filingDate'][i] for i in k8_indices]
        print(f"8-K filingDate range: {min(dates)} to {max(dates)}")
        in_range = [i for i in k8_indices if '2019-01-01' <= recent['filingDate'][i] <= '2020-06-10']
        print(f"8-Ks in 2019-01-01 to 2020-06-10: {len(in_range)}")
        # Check files property (files array for older filings)
        files = d.get('filings', {}).get('files', [])
        print(f"Additional files in filings: {len(files)}")
