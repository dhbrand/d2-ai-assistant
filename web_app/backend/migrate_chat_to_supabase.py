import os
import sqlite3
from supabase import create_client, Client
from dotenv import load_dotenv
import uuid
from datetime import datetime

# --- Configuration ---
# Load environment variables from .env file (optional, if you store Supabase creds there)
# load_dotenv()

# Local Supabase credentials (from 'supabase start' output)
# IMPORTANT: These are for your LOCAL Supabase instance.
# For a real cloud migration, use your cloud project's URL and service_role_key.
SUPABASE_URL = "http://127.0.0.1:54321"  # Or os.getenv("LOCAL_SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU" # Or os.getenv("LOCAL_SUPABASE_SERVICE_ROLE_KEY")

SQLITE_DB_PATH = "./chat_history.db"  # Path relative to where this script is run (web_app/backend/)

def get_sqlite_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row  # Access columns by name
        print(f"Successfully connected to SQLite: {SQLITE_DB_PATH}")
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to SQLite: {e}")
        raise

def get_supabase_client() -> Client:
    """Initializes and returns the Supabase client."""
    try:
        client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        print(f"Successfully connected to Supabase: {SUPABASE_URL}")
        return client
    except Exception as e:
        print(f"Error connecting to Supabase: {e}")
        raise

def migrate_conversations(sqlite_conn, supabase_client: Client):
    """Migrates data from SQLite 'conversations' to Supabase 'conversations'."""
    print("\n--- Migrating Conversations ---")
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT id, user_bungie_id, title, created_at, updated_at, archived FROM conversations")
    sqlite_conversations = cursor.fetchall()

    if not sqlite_conversations:
        print("No conversations found in SQLite to migrate.")
        return

    conversations_to_insert = []
    for row in sqlite_conversations:
        # Ensure created_at and updated_at are timezone-aware if possible, or handle appropriately
        # Supabase expects timestamptz. SQLite might store naive datetimes or strings.
        # For simplicity, we assume they are UTC or can be treated as such.
        # If they are strings, parse them: datetime.fromisoformat(row['created_at'])
        created_at_val = row['created_at']
        updated_at_val = row['updated_at']

        # Convert string UUIDs from SQLite to Python UUID objects if needed, then to string for Supabase
        # Supabase client handles Python UUID objects correctly for uuid columns.
        try:
            convo_id = uuid.UUID(row['id'])
        except (ValueError, TypeError):
            print(f"Warning: Could not parse SQLite conversation ID {row['id']} as UUID. Generating new one.")
            convo_id = uuid.uuid4()


        conversations_to_insert.append({
            "id": str(convo_id), # Supabase client expects string for UUIDs or Python UUID object
            "user_id": row['user_bungie_id'], # Map user_bungie_id to user_id
            "created_at": created_at_val,
            # title, updated_at, archived are optional or have defaults in Supabase,
            # but we migrate them if present
            "title": row['title'] if row['title'] else None,
            # "updated_at": updated_at_val, # Supabase schema has default onupdate
            # "archived": bool(row['archived']) # Supabase schema has default
        })
        if row['title']: # Only include if not None
            conversations_to_insert[-1]['title'] = row['title']
        # Supabase schema handles updated_at and archived defaults/onupdate,
        # so we might not need to explicitly set them unless we want to preserve exact SQLite values.
        # For `archived`, SQLite stores 0/1, Supabase expects true/false.
        if 'archived' in row.keys() and row['archived'] is not None:
             conversations_to_insert[-1]['archived'] = bool(row['archived'])


    if conversations_to_insert:
        print(f"Attempting to insert {len(conversations_to_insert)} conversations into Supabase...")
        try:
            response = supabase_client.table("conversations").insert(conversations_to_insert).execute()
            # For inserts, success is often indicated by response.data being a list of the inserted items.
            # If an HTTP error occurs (e.g., 4xx, 5xx), supabase-py usually raises an exception.
            if response.data and isinstance(response.data, list):
                print(f"Successfully inserted {len(response.data)} conversations.")
            else:
                # This case might indicate a problem if data was expected but not returned,
                # or if the response structure for errors without HTTP exceptions is different.
                print("Conversation insert call executed. Response data did not indicate clear success or was empty.")
                print(f"Response: {response}") # Log the whole response for inspection
        except Exception as e:
            print(f"Exception during Supabase insert for conversations: {e}")
    else:
        print("No conversations formatted for Supabase insertion.")


def migrate_messages(sqlite_conn, supabase_client: Client):
    """Migrates data from SQLite 'messages' to Supabase 'messages'."""
    print("\n--- Migrating Messages ---")
    cursor = sqlite_conn.cursor()
    # Select all relevant columns. Ensure timestamp is handled.
    cursor.execute("SELECT id, conversation_id, order_index, role, content, timestamp FROM messages ORDER BY conversation_id, order_index")
    sqlite_messages = cursor.fetchall()

    if not sqlite_messages:
        print("No messages found in SQLite to migrate.")
        return

    messages_to_insert = []
    for row in sqlite_messages:
        # Map SQLite columns to Supabase columns
        # Handle timestamp: SQLite 'timestamp' maps to Supabase 'created_at'
        # Parse if it's a string: datetime.fromisoformat(row['timestamp'])
        created_at_val = row['timestamp']

        try:
            msg_id = uuid.UUID(row['id'])
        except (ValueError, TypeError):
            print(f"Warning: Could not parse SQLite message ID {row['id']} as UUID. Generating new one.")
            msg_id = uuid.uuid4()
        
        try:
            convo_id_for_msg = uuid.UUID(row['conversation_id'])
        except (ValueError, TypeError):
            print(f"Warning: Could not parse SQLite conversation_id {row['conversation_id']} for message {msg_id}. Skipping message.")
            continue


        messages_to_insert.append({
            "id": str(msg_id),
            "conversation_id": str(convo_id_for_msg),
            "sender": row['role'],  # 'role' in SQLite maps to 'sender' in Supabase
            "content": row['content'],
            "created_at": created_at_val
            # 'order_index' is not in the current Supabase 'messages' schema.
            # If order is critical and only derivable from order_index,
            # you might need to add it to Supabase or ensure created_at is granular enough.
        })

    if messages_to_insert:
        print(f"Attempting to insert {len(messages_to_insert)} messages into Supabase...")
        try:
            response = supabase_client.table("messages").insert(messages_to_insert).execute()
            if response.data and isinstance(response.data, list):
                print(f"Successfully inserted {len(response.data)} messages.")
            else:
                print("Message insert call executed. Response data did not indicate clear success or was empty.")
                print(f"Response: {response}") # Log the whole response for inspection
        except Exception as e:
            print(f"Exception during Supabase insert for messages: {e}")
            
    else:
        print("No messages formatted for Supabase insertion.")

def main():
    """Main function to orchestrate the migration."""
    print("Starting chat history migration from SQLite to Supabase (Local)...")
    
    sqlite_conn = None
    try:
        sqlite_conn = get_sqlite_connection()
        supabase_client = get_supabase_client()

        # It's often safer to migrate conversations first due to foreign key constraints
        migrate_conversations(sqlite_conn, supabase_client)
        migrate_messages(sqlite_conn, supabase_client)

        print("\nMigration process finished.")
        print("Please verify the data in your local Supabase Studio (http://127.0.0.1:54323).")

    except Exception as e:
        print(f"An error occurred during the migration process: {e}")
    finally:
        if sqlite_conn:
            sqlite_conn.close()
            print("SQLite connection closed.")

if __name__ == "__main__":
    # Ensure the script is run from the 'web_app/backend' directory
    # or adjust SQLITE_DB_PATH accordingly.
    # If this script is in web_app/backend, and chat_history.db is also there,
    # SQLITE_DB_PATH = "./chat_history.db" is correct.
    # If chat_history.db is in web_app/backend/data, it would be "./data/chat_history.db"
    
    # Verify SQLite DB path before running
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"ERROR: SQLite database not found at {os.path.abspath(SQLITE_DB_PATH)}")
        print("Please ensure the SQLITE_DB_PATH is correct and the script is run from the expected directory (e.g., web_app/backend).")
    else:
        main() 