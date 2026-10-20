"""
Independently audit and verify the ZIP Central Directory of full_history.zip.
"""

import struct
import io
import zipfile
import requests
from collections import Counter

HF_RAW_BASE = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main"
zip_url = f"{HF_RAW_BASE}/Stock_price/full_history.zip"

print(f"Connecting to: {zip_url}")
r_head = requests.head(zip_url, allow_redirects=True, timeout=30)
total_size = int(r_head.headers.get("Content-Length", 0))
print(f"Content-Length: {total_size:,} bytes")

# 1. Fetch the last 65KB to locate EOCD record
tail_size = min(65 * 1024, total_size)
r_tail = requests.get(zip_url, headers={"Range": f"bytes={total_size - tail_size}-{total_size - 1}"}, allow_redirects=True, timeout=30)
tail_data = r_tail.content

eocd_pos = tail_data.rfind(b"PK\x05\x06")
if eocd_pos == -1:
    raise ValueError("EOCD signature PK\\x05\\x06 not found!")

eocd = tail_data[eocd_pos:eocd_pos + 22]
disk_num, cd_disk, disk_entries, total_entries, cd_size, cd_offset = struct.unpack("<HHHHII", eocd[4:20])
comment_len = struct.unpack("<H", eocd[20:22])[0]

print("\n--- EOCD RECORD HEADER (Standard ZIP) ---")
print(f"Disk number: {disk_num}")
print(f"CD start disk: {cd_disk}")
print(f"Entries on disk: {disk_entries:,}")
print(f"Total entries: {total_entries:,}")
print(f"CD size: {cd_size:,} bytes")
print(f"CD offset: {cd_offset:,} (relative to byte 0)")
print(f"Comment length: {comment_len}")
print(f"Expected end of CD: {cd_offset + cd_size:,}")
print(f"Distance from end of CD to EOF: {total_size - (cd_offset + cd_size)} bytes")

# 2. Check for Zip64 EOCD Locator
zip64_loc_pos = tail_data.rfind(b"PK\x06\x07")
print(f"Zip64 Locator present? {zip64_loc_pos != -1}")

# 3. Fetch the exact Central Directory range: [cd_offset, cd_offset + cd_size - 1]
print(f"\nFetching exact Central Directory bytes: {cd_offset} to {cd_offset + cd_size - 1}...")
headers = {"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"}
r_cd = requests.get(zip_url, headers=headers, allow_redirects=True, timeout=90)
cd_data = r_cd.content
print(f"Downloaded CD bytes: {len(cd_data):,} (expected {cd_size:,})")

# 4. Parse all Central Directory file headers (signature PK\x01\x02)
pos = 0
entries = []
malformed = 0

while pos < len(cd_data):
    sig = cd_data[pos:pos+4]
    if sig != b"PK\x01\x02":
        print(f"Stopped parsing at offset {pos:,}: signature is {sig}")
        break
    if pos + 46 > len(cd_data):
        print(f"Incomplete header at offset {pos:,}")
        break
    
    version_made = struct.unpack("<H", cd_data[pos+4:pos+6])[0]
    version_need = struct.unpack("<H", cd_data[pos+6:pos+8])[0]
    flags = struct.unpack("<H", cd_data[pos+8:pos+10])[0]
    method = struct.unpack("<H", cd_data[pos+10:pos+12])[0]
    time = struct.unpack("<H", cd_data[pos+12:pos+14])[0]
    date = struct.unpack("<H", cd_data[pos+14:pos+16])[0]
    crc = struct.unpack("<I", cd_data[pos+16:pos+20])[0]
    comp_size = struct.unpack("<I", cd_data[pos+20:pos+24])[0]
    uncomp_size = struct.unpack("<I", cd_data[pos+24:pos+28])[0]
    fname_len = struct.unpack("<H", cd_data[pos+28:pos+30])[0]
    extra_len = struct.unpack("<H", cd_data[pos+30:pos+32])[0]
    comment_len = struct.unpack("<H", cd_data[pos+32:pos+34])[0]
    local_offset = struct.unpack("<I", cd_data[pos+42:pos+46])[0]
    
    fname = cd_data[pos+46:pos+46+fname_len].decode("utf-8", errors="replace")
    
    entries.append({
        "filename": fname,
        "comp_size": comp_size,
        "uncomp_size": uncomp_size,
        "local_offset": local_offset,
    })
    
    pos += 46 + fname_len + extra_len + comment_len

print(f"\n--- CD PARSE RESULTS ---")
print(f"Total entries parsed: {len(entries):,}")
print(f"Did parser reach exact end of CD? {pos == len(cd_data)} (pos={pos:,}, len={len(cd_data):,})")

# 5. Classify entries
categories = Counter()
filenames = [e["filename"] for e in entries]

for fn in filenames:
    if fn.startswith("__MACOSX/"):
        categories["macosx_resource_fork"] += 1
    elif fn == "full_history/":
        categories["directory"] += 1
    elif fn.startswith("full_history/") and fn.endswith(".csv"):
        categories["full_history_csv"] += 1
    else:
        categories["other"] += 1

print("\n--- ENTRY CLASSIFICATION ---")
for cat, count in categories.items():
    print(f"  {cat}: {count:,}")

# 6. Extract valid tickers
valid_csvs = [e for e in entries if e["filename"].startswith("full_history/") and not e["filename"].startswith("full_history/._") and e["filename"].endswith(".csv")]
print(f"\nTotal valid full_history CSV files: {len(valid_csvs):,}")

# Check for duplicate filenames
fn_counts = Counter([e["filename"] for e in valid_csvs])
dupe_fns = {k: v for k, v in fn_counts.items() if v > 1}
print(f"Duplicate filenames in valid CSVs: {len(dupe_fns)}")

# Check ticker casing
raw_symbols = [e["filename"][len("full_history/"): -4] for e in valid_csvs]
upper_symbols = set(s.upper() for s in raw_symbols)
print(f"Raw ticker symbols extracted: {len(raw_symbols):,}")
print(f"Unique uppercase ticker symbols: {len(upper_symbols):,}")

# Check if there are any case collisions
case_map = {}
for s in raw_symbols:
    u = s.upper()
    if u not in case_map:
        case_map[u] = set()
    case_map[u].add(s)

case_collisions = {k: v for k, v in case_map.items() if len(v) > 1}
print(f"Case collisions (e.g. both 'a.csv' and 'A.csv'): {len(case_collisions)}")
if case_collisions:
    print(f"Sample case collisions: {list(case_collisions.items())[:5]}")
