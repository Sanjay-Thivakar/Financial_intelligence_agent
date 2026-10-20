import pandas as pd

uni = pd.read_parquet('data/processed/universe/sp500_universe.parquet')
for tk in ['AAPL', 'JPM', 'GOOG', 'TSLA', 'AA']:
    sub = uni[uni['ticker'] == tk]
    print(f'Ticker: {tk}, count: {len(sub)}')
    for _, r in sub.iterrows():
        print(f"  cid={r.get('company_id')}, cik={r.get('cik')}, name={r.get('company_name')}, from={r.get('effective_from')}, to={r.get('effective_to')}")
