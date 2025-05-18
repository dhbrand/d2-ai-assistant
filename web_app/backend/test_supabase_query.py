import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
    exit(1)

sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

bungie_id = "29565467"
try:
    # Query the new public.profiles table
    resp = sb_admin.table("profiles").select("*").eq("bungie_id", bungie_id).maybe_single().execute()
    print("Query result:", resp.data)
except Exception as e:
    print("Query error:", e) 