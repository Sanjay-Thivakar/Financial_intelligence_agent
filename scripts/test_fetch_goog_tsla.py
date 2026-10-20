from src.data.sec.fetcher import SECFetcher

fetcher = SECFetcher()
print("Fetcher initialized with user-agent:", fetcher.user_agent)

# Test fetch submissions for GOOG
goog_sub = fetcher.fetch_submissions("0001652044")
print("GOOG name:", goog_sub.get("name"), "filing count in recent:", len(goog_sub.get("filings", {}).get("recent", {}).get("form", [])))
forms = goog_sub.get("filings", {}).get("recent", {}).get("form", [])
k8_goog = [i for i, f in enumerate(forms) if f in ("8-K", "8-K/A")]
dates_goog = [goog_sub["filings"]["recent"]["filingDate"][i] for i in k8_goog]
if dates_goog:
    print(f"GOOG 8-Ks: {len(k8_goog)}, range: {min(dates_goog)} to {max(dates_goog)}")
    in_range = [i for i in k8_goog if "2019-01-01" <= goog_sub["filings"]["recent"]["filingDate"][i] <= "2020-06-10"]
    print(f"GOOG 8-Ks in 2019-01-01 to 2020-06-10: {len(in_range)}")
    print("GOOG files in filings:", len(goog_sub.get("filings", {}).get("files", [])))

# Test fetch submissions for TSLA
tsla_sub = fetcher.fetch_submissions("0001318605")
print("TSLA name:", tsla_sub.get("name"), "filing count in recent:", len(tsla_sub.get("filings", {}).get("recent", {}).get("form", [])))
forms_tsla = tsla_sub.get("filings", {}).get("recent", {}).get("form", [])
k8_tsla = [i for i, f in enumerate(forms_tsla) if f in ("8-K", "8-K/A")]
dates_tsla = [tsla_sub["filings"]["recent"]["filingDate"][i] for i in k8_tsla]
if dates_tsla:
    print(f"TSLA 8-Ks: {len(k8_tsla)}, range: {min(dates_tsla)} to {max(dates_tsla)}")
    in_range = [i for i in k8_tsla if "2019-01-01" <= tsla_sub["filings"]["recent"]["filingDate"][i] <= "2020-06-10"]
    print(f"TSLA 8-Ks in 2019-01-01 to 2020-06-10: {len(in_range)}")
    print("TSLA files in filings:", len(tsla_sub.get("filings", {}).get("files", [])))
