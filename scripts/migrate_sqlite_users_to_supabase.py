import csv
import asyncio
import os
from datetime import datetime
from supabase import create_async_client, AsyncClient

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
CSV_FILE = "users_for_supabase_migration.csv"

async def migrate_users():
    sb_client: AsyncClient = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
    successes = 0
    failures = 0
    with open(CSV_FILE, newline="") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if not row or row[0] == "id":
                continue  # skip header or empty
            _, bungie_id, supabase_uuid, access_token, refresh_token, access_token_expires = row
            if not supabase_uuid:
                print(f"Skipping user with Bungie ID {bungie_id}: no supabase_uuid")
                continue
            metadata_update = {
                "bungie_id": bungie_id,
                "bungie_access_token": access_token,
                "bungie_refresh_token": refresh_token,
                "bungie_token_expires": access_token_expires or None
            }
            try:
                resp = await sb_client.table("profiles").update({"raw_user_meta_data": metadata_update}).eq("id", supabase_uuid).execute()
                if resp.error:
                    print(f"Failed to update user {supabase_uuid}: {resp.error}")
                    failures += 1
                else:
                    print(f"Updated user {supabase_uuid} with Bungie ID {bungie_id}")
                    successes += 1
            except Exception as e:
                print(f"Exception updating user {supabase_uuid}: {e}")
                failures += 1
    print(f"Migration complete. Successes: {successes}, Failures: {failures}")

if __name__ == "__main__":
    asyncio.run(migrate_users()) 