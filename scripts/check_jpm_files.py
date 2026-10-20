import json

with open("data/raw/sec/submissions/CIK0000019617.json", encoding="utf-8") as f:
    d = json.load(f)

files = d.get("filings", {}).get("files", [])
print(f"JPM has {len(files)} files.")
matching_files = []
for file_info in files:
    f_from = file_info.get("filingFrom")
    f_to = file_info.get("filingTo")
    # check if overlap with 2019-01-01 to 2020-06-10
    if not (f_to < "2019-01-01" or f_from > "2020-06-10"):
        matching_files.append(file_info)

print(f"Matching files for JPM in 2019-2020 window: {len(matching_files)}")
for mf in matching_files:
    print(" ", mf)
