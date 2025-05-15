from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SERVICE_ACCOUNT_FILE = "service_account.json"  # <-- Your downloaded service account key
SPREADSHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"

def main():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    try:
        service = build("sheets", "v4", credentials=creds)
        meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = meta.get("sheets", [])
        print("Active sheets in spreadsheet:")
        for s in sheets:
            title = s["properties"]["title"]
            gid = s["properties"]["sheetId"]
            if "old" not in title.lower() and "outdated" not in title.lower():
                print(f"- {title} (gid: {gid})")
    except HttpError as err:
        print(err)

if __name__ == "__main__":
    main() 