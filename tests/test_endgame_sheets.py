import pandas as pd
import requests
import xml.etree.ElementTree as ET

SHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"

# Step 1: Fetch all sheet names and gids from the public worksheet feed
worksheet_feed_url = f"https://spreadsheets.google.com/feeds/worksheets/{SHEET_ID}/public/full"
resp = requests.get(worksheet_feed_url)
print(f"HTTP status code: {resp.status_code}")
print("First 1000 characters of response:")
print(resp.text[:1000])

if resp.status_code != 200:
    print("ERROR: Did not get a 200 OK from Google. Exiting.")
    exit(1)

try:
    root = ET.fromstring(resp.content)
except Exception as e:
    print(f"XML parsing error: {e}")
    exit(1)

ns = {'atom': 'http://www.w3.org/2005/Atom'}
all_sheets = {}
for entry in root.findall('atom:entry', ns):
    title = entry.find('atom:title', ns).text
    gid = entry.find('atom:id', ns).text.split('/')[-1]
    all_sheets[title] = gid
print("All sheets detected:")
for name, gid in all_sheets.items():
    print(f"  {name}: gid={gid}")

# Step 2: Fetch the Status sheet as CSV to determine active sheets
status_gid = all_sheets.get('Status')
if not status_gid:
    print("ERROR: Could not find 'Status' sheet in spreadsheet.")
    exit(1)
status_csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={status_gid}"
status_df = pd.read_csv(status_csv_url)
print("\nStatus sheet preview:")
print(status_df.head())

# Step 3: Identify active sheets (not archived/future)
if 'STATUS' not in status_df.columns or 'TAB' not in status_df.columns:
    print("ERROR: 'STATUS' or 'TAB' column missing in Status sheet.")
    exit(1)
active_sheets = status_df[status_df['STATUS'].str.lower() == 'updated']['TAB'].tolist()
active_sheets = [s for s in active_sheets if s in all_sheets]
print("\nActive sheets detected:")
for name in active_sheets:
    print(f"  {name}: gid={all_sheets[name]}")

if not active_sheets:
    print("WARNING: No active sheets detected. Check the STATUS column values in the Status sheet.") 