import os
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import uuid
from datetime import datetime, timezone

# --- Load Environment Variables ---
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.env'))
print(f"Attempting to load environment variables from: {dotenv_path}")
loaded = load_dotenv(dotenv_path=dotenv_path)
if not loaded:
    print(f"CRITICAL: .env file not found at {dotenv_path}. Please ensure it exists and has SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    exit(1)
else:
    print(".env file loaded successfully.")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("CRITICAL: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment variables.")
    exit(1)

print(f"Using SUPABASE_URL: {SUPABASE_URL}")
# For security, don't print the key in production logs, but fine for this local test script
# print(f"Using SUPABASE_KEY: {SUPABASE_KEY[:5]}...") 

def run_crud_test():
    sb_client: Client = None
    try:
        print("\nInitializing Supabase client...")
        # Explicitly set schema to public if needed, though it's usually default
        options = ClientOptions(schema="public") 
        sb_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=options)
        print("Supabase client initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Supabase client: {e}")
        return

    test_conversation_id = str(uuid.uuid4())
    test_user_id = "test_crud_user_001" 
    initial_title = "CRUD Test Initial Title"
    updated_title = "CRUD Test Updated Title"

    try:
        # 1. CREATE (Insert)
        print(f"\n--- 1. CREATE operation for conversation ID: {test_conversation_id} ---")
        insert_data = {
            "id": test_conversation_id,
            "user_id": test_user_id, # Matches the column name in your Supabase table
            "title": initial_title,
            "archived": False, # Assuming this is a required field with a default
            # created_at and updated_at should be handled by db defaults if set up
        }
        response = sb_client.table("conversations").insert(insert_data).execute()
        print(f"CREATE response status: {response.data is not None} (checking if data exists in response)") # Supabase-py v1 inserts return data
        if response.data and len(response.data) > 0:
            print(f"CREATE successful. Inserted data: {response.data[0]}")
        else:
            print(f"CREATE failed or returned no data. Full response: {response}")
            # Try to get more error info if available
            if hasattr(response, 'error') and response.error:
                print(f"Error details: {response.error}")
            return # Stop test if create fails

        # 2. READ (Select after create)
        print(f"\n--- 2. READ operation for conversation ID: {test_conversation_id} ---")
        response = sb_client.table("conversations").select("*").eq("id", test_conversation_id).maybe_single().execute()
        if response.data:
            print(f"READ successful. Fetched data: {response.data}")
            assert response.data['id'] == test_conversation_id
            assert response.data['title'] == initial_title
            assert response.data['user_id'] == test_user_id
        else:
            print(f"READ failed. Could not fetch conversation {test_conversation_id}.")
            if hasattr(response, 'error') and response.error:
                print(f"Error details: {response.error}")
            return

        # 3. UPDATE
        print(f"\n--- 3. UPDATE operation for conversation ID: {test_conversation_id} ---")
        update_payload = {"title": updated_title, "updated_at": datetime.now(timezone.utc).isoformat()}
        response = sb_client.table("conversations").update(update_payload).eq("id", test_conversation_id).execute()
        print(f"UPDATE response status: {response.data is not None}")
        if response.data and len(response.data) > 0:
            print(f"UPDATE successful. Updated data: {response.data[0]}")
            assert response.data[0]['title'] == updated_title
        else:
            print(f"UPDATE failed or returned no data. Full response: {response}")
            if hasattr(response, 'error') and response.error:
                print(f"Error details: {response.error}")
            return

        # 4. READ (Select after update)
        print(f"\n--- 4. READ operation (after update) for conversation ID: {test_conversation_id} ---")
        response = sb_client.table("conversations").select("*").eq("id", test_conversation_id).maybe_single().execute()
        if response.data:
            print(f"READ successful. Fetched data: {response.data}")
            assert response.data['title'] == updated_title
        else:
            print(f"READ failed. Could not fetch conversation {test_conversation_id} after update.")
            if hasattr(response, 'error') and response.error:
                print(f"Error details: {response.error}")
            return

    except Exception as e:
        print(f"\nAN EXCEPTION OCCURRED DURING CRUD TEST: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 5. DELETE (Cleanup)
        if sb_client: # Ensure client was initialized
            print(f"\n--- 5. DELETE operation for conversation ID: {test_conversation_id} ---")
            try:
                # Check if the record exists before attempting to delete, to avoid errors if create failed
                check_response = sb_client.table("conversations").select("id").eq("id", test_conversation_id).maybe_single().execute()
                if check_response.data:
                    response = sb_client.table("conversations").delete().eq("id", test_conversation_id).execute()
                    print(f"DELETE response status: {response.data is not None}")
                    if response.data and len(response.data) > 0:
                        print(f"DELETE successful for conversation {test_conversation_id}. Deleted data: {response.data[0]}")
                    else:
                        print(f"DELETE failed or returned no data for {test_conversation_id}. Full response: {response}")
                        if hasattr(response, 'error') and response.error:
                            print(f"Error details: {response.error}")
                else:
                    print(f"Skipping DELETE as conversation {test_conversation_id} was not found (likely create/previous step failed).")

                # 6. VERIFY DELETION (Select after delete)
                print(f"\n--- 6. VERIFY DELETION for conversation ID: {test_conversation_id} ---")
                response = sb_client.table("conversations").select("*").eq("id", test_conversation_id).maybe_single().execute()
                if not response.data:
                    print(f"VERIFY DELETION successful. Conversation {test_conversation_id} not found.")
                else:
                    print(f"VERIFY DELETION failed. Conversation {test_conversation_id} still exists: {response.data}")
                    if hasattr(response, 'error') and response.error:
                        print(f"Error details: {response.error}")
            except Exception as e_cleanup:
                print(f"EXCEPTION during cleanup (DELETE): {e_cleanup}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    run_crud_test() 