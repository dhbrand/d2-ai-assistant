from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SERVICE_ACCOUNT_FILE = "service_account.json"  # <-- Your downloaded service account key
SPREADSHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"
STATUS_SHEET_NAME = "Status"

def main():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    try:
        service = build("sheets", "v4", credentials=creds)
        # 1. List all sheet/tab names and their GIDs
        meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = meta.get("sheets", [])
        print("All sheets in spreadsheet:")
        sheet_gid_map = {}
        for s in sheets:
            title = s["properties"]["title"]
            gid = s["properties"]["sheetId"]
            print(f"- {title} (gid: {gid})")
            sheet_gid_map[title] = gid
        # 2. Read the Status sheet
        status_range = f"{STATUS_SHEET_NAME}!A1:Z"
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=status_range
        ).execute()
        values = result.get("values", [])
        if not values:
            print("No data found in Status sheet.")
            return
        # Find the columns for sheet name and status
        headers = values[0]
        try:
            name_idx = headers.index("SHEET")
            status_idx = headers.index("STATUS")
        except ValueError:
            print("Could not find 'SHEET' or 'STATUS' columns in Status sheet.")
            return
        print("\nActive sheets (not archived):")
        for row in values[1:]:
            if len(row) > max(name_idx, status_idx):
                sheet_name = row[name_idx]
                status = row[status_idx].strip().lower()
                if status == "active":
                    print(f"- {sheet_name} (gid: {sheet_gid_map.get(sheet_name, 'N/A')})")
    except HttpError as err:
        print(err)

if __name__ == "__main__":
    main()
