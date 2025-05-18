from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Query, Header, BackgroundTasks, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta, timezone
import os
import logging
from jose import JWTError, jwt
from requests.exceptions import HTTPError
import requests
import httpx # Import httpx
import json
import time
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import threading
from collections import defaultdict
import uuid
import asyncio # <-- Import asyncio
from openai import AsyncOpenAI # <-- Import OpenAI client
from jose.exceptions import ExpiredSignatureError
from supabase import create_client, Client, ClientOptions # <-- Add Supabase imports
from supabase import create_async_client, AsyncClient # <-- Add async Supabase imports

# Use absolute imports
from web_app.backend.bungie_oauth import OAuthManager, InvalidRefreshTokenError, TokenData, AuthenticationRequiredError # Import TokenData here
from web_app.backend.catalyst_api import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.agent_service import DestinyAgentService
from .manifest import SupabaseManifestService # Import the new service
from web_app.backend.performance_logging import log_api_performance  # Import the profiling helper
from web_app.backend.models import CallbackData, UserResponse, ConversationSchema, ChatMessageSchema

# Configure logging to file and console
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "app.log")

# Remove all handlers if reloading (for dev hot reload)
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(name)s:%(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='w'),  # Overwrite on each start
        logging.StreamHandler()  # Console
    ]
)
logger = logging.getLogger(__name__)

# --- Pydantic Models for Chat (Moved Up) ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    previous_response_id: Optional[str] = None
    token_data: Optional[TokenData] = None
    model_name: Optional[str] = None
    conversation_id: Optional[uuid.UUID] = None # Add conversation ID
    persona: Optional[str] = None  # <-- Add persona support

class ChatResponse(BaseModel):
    message: ChatMessage
    response_id: Optional[str] = None
    conversation_id: uuid.UUID # Always return conversation ID

# --- Pydantic model for listing models ---
class ModelInfo(BaseModel):
    id: str

class ModelListResponse(BaseModel):
    models: List[ModelInfo]

# --- End Moved Models ---

# --- Environment Variables and Configuration ---
BUNGIE_CLIENT_ID = os.getenv("BUNGIE_CLIENT_ID")
BUNGIE_CLIENT_SECRET = os.getenv("BUNGIE_CLIENT_SECRET")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_secret_key_for_dev_only") # Use env var for production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours
DATABASE_URL = "sqlite:///./catalysts.db"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Uncomment
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

if not all([BUNGIE_CLIENT_ID, BUNGIE_CLIENT_SECRET, BUNGIE_API_KEY]):
    logger.error("Missing one or more Bungie environment variables!")
    # Depending on setup, might want to exit or raise an exception here
    # raise ValueError("Missing Bungie environment variables")

# --- Supabase Client Initialization ---
# Use environment variables for Supabase credentials
# These should be set in your .env file
SUPABASE_URL = os.getenv("SUPABASE_URL") # <-- Use name from .env
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # <-- Use name from .env

supabase_client: Optional[AsyncClient] = None # <-- Initialize to None
supabase_manifest_service: Optional[SupabaseManifestService] = None # <-- Initialize to None

# --- Supabase Admin Client (for backend-only operations) ---
sb_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    try:
        sb_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("Supabase ADMIN client initialized for backend operations.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase ADMIN client: {e}")
        sb_admin = None
else:
    logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment variables. Supabase admin operations will not be available.")

# --- FastAPI App Instance ---
app = FastAPI(
    title="Destiny 2 Catalyst Tracker & AI Assistant",
    description="An application to track Destiny 2 weapon catalysts and interact with an AI assistant for Destiny 2 information.",
    version="0.2.0",
    # lifespan=lifespan # Use lifespan if on FastAPI 0.90.0+
)

# --- Timing Middleware ---
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"Request {request.method} {request.url.path} completed in {process_time:.4f} secs") # Log process time
    return response
# --- End Timing Middleware ---

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:3000", "http://localhost:3000"], # Allow dev frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Globals / Clients (Should only contain placeholders filled by startup) ---
# supabase_client is initialized earlier
# supabase_manifest_service is initialized earlier
oauth_manager: Optional[OAuthManager] = None
openai_client = None # Initialized globally earlier, but can be re-confirmed or modified in startup
agent_service_instance = None # Removed: agent_service_instance: Optional[DestinyAgentService] = None
catalyst_api_instance: Optional[CatalystAPI] = None
weapon_api_instance: Optional[WeaponAPI] = None
# scheduler = BackgroundScheduler() # Keep scheduler if used

# --- FastAPI Startup Event --- 
@app.on_event("startup")
async def startup_event():
    """Run initialization tasks when the application starts."""
    logger.info(f"Startup running in PID: {os.getpid()}")
    logger.info("Running application startup tasks...")
    # Declare all globals that are referenced or assigned to within this function
    global oauth_manager, supabase_client, supabase_manifest_service, openai_client, catalyst_api_instance, weapon_api_instance

    # Initialize Supabase Client and Manifest Service FIRST
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            # Use create_async_client for an asynchronous client
            supabase_client = await create_async_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Supabase ASYNC client initialized in startup.")

            # Initialize SupabaseManifestService (depends on supabase_client)
            supabase_manifest_service = SupabaseManifestService(sb_client=supabase_client)
            logger.info("SupabaseManifestService initialized with ASYNC client in startup.")

        except Exception as e:
            logger.exception(f"Error initializing Supabase client or SupabaseManifestService in startup: {e}")
            # supabase_client and supabase_manifest_service will remain None
    else:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment variables. Supabase services will not be available.")

    # Initialize OAuthManager
    try:
        oauth_manager = OAuthManager()
        logger.info("OAuthManager initialized.")
    except Exception as e:
        logger.exception(f"Error initializing OAuthManager: {e}")
        oauth_manager = None

    # Supabase client and manifest service are initialized above.
    # We now proceed to initialize services that depend on them.

    # ADD DETAILED LOGGING HERE
    logger.info(f"[STARTUP_CHECK] oauth_manager type: {type(oauth_manager)}, bool: {bool(oauth_manager)}")
    logger.info(f"[STARTUP_CHECK] supabase_manifest_service type: {type(supabase_manifest_service)}, bool: {bool(supabase_manifest_service)}")

    if oauth_manager and supabase_manifest_service:
        try:
            logger.info("Attempting to initialize CatalystAPI and WeaponAPI...")
            catalyst_api_instance = CatalystAPI(oauth_manager=oauth_manager, manifest_service=supabase_manifest_service)
            logger.info("CatalystAPI instance created.")
            weapon_api_instance = WeaponAPI(oauth_manager=oauth_manager, manifest_service=supabase_manifest_service)
            logger.info("WeaponAPI instance created.")
        except Exception as e:
            logger.exception(f"Error initializing CatalystAPI or WeaponAPI: {e}")
            # Ensure they are None on failure if they were partially assigned
            catalyst_api_instance = None
            weapon_api_instance = None
    else:
        logger.error("OAuthManager or SupabaseManifestService not available. Cannot initialize CatalystAPI or WeaponAPI.")

    # Initialize AgentService with the API instances
    if openai_client and catalyst_api_instance and weapon_api_instance and supabase_client:
        try:
            logger.info("Attempting to initialize DestinyAgentService...")
            agent_service = DestinyAgentService(
                openai_client=openai_client,
                catalyst_api=catalyst_api_instance,
                weapon_api=weapon_api_instance,
                sb_client=supabase_client,
                manifest_service=supabase_manifest_service
            )
            app.state.agent_service_instance = agent_service
            logger.info("DestinyAgentService initialized and stored in app.state.")
        except Exception as e:
            logger.exception(f"Error initializing DestinyAgentService: {e}")
            app.state.agent_service_instance = None
    else:
        missing_deps = []
        if not openai_client: missing_deps.append("OpenAI Client (global)")
        if not catalyst_api_instance: missing_deps.append("CatalystAPI (global)")
        if not weapon_api_instance: missing_deps.append("WeaponAPI (global)")
        if not supabase_client: missing_deps.append("Supabase Client (global)")
        logger.error(f"DestinyAgentService could not be initialized. Missing: {', '.join(missing_deps)}")
        app.state.agent_service_instance = None

    logger.info("Application startup tasks finished.")

# --- Caching Setup ---
CACHE_DURATION = timedelta(minutes=5)

WEAPON_CACHE_DURATION = timedelta(minutes=10) # Add weapon cache duration

# In-memory mapping: user_id -> thread_id (for demo; replace with DB for production)
user_thread_map = defaultdict(str)
user_thread_lock = threading.Lock()

# --- Dependency Functions ---
def get_db_session():
    global db_session_local # Access the global session factory
    if db_session_local is None:
        logger.error("Database session factory (db_session_local) is not configured.")
        raise HTTPException(status_code=503, detail="Database session not available.")
    db = db_session_local() # Call the factory to get a session
    try:
        yield db
    finally:
        db.close()

# --- Dependency Function for Supabase Client ---
async def get_supabase_db() -> AsyncClient:
    """Dependency to get the initialized Supabase async client."""
    global supabase_client # Ensure we are referring to the global instance
    if not supabase_client:
        logger.error("Supabase client not initialized. Check server logs and .env configuration.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not initialized. Check server configuration."
        )
    return supabase_client

# --- NEW Dependency Function for Chat History DB ---
def get_chat_db():
    """Dependency to get a session for the chat history database."""
    db = ChatHistorySessionLocal()
    try:
        yield db
    finally:
        db.close()
# --- End NEW Dependency Function ---

# Use the standard scheme but expect the JWT in the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/dummy_token_url")

class SupabaseUser(BaseModel):
    uuid: str
    bungie_id: Optional[str] = None

async def get_supabase_user_from_token(jwt_token: str = Depends(oauth2_scheme)) -> SupabaseUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_uuid: str = payload.get("sub")
        bungie_id: Optional[str] = payload.get("bng")
        if not user_uuid:
            raise credentials_exception
        return SupabaseUser(uuid=user_uuid, bungie_id=bungie_id)
    except Exception as e:
        logger.error(f"JWT decode failed: {e}")
        raise credentials_exception

# --- API Endpoints ---

@app.get("/auth/url")
def get_auth_url():
    """Get the Bungie OAuth authorization URL"""
    try:
        auth_url = oauth_manager.get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/callback")
async def handle_auth_callback(callback_data: CallbackData, request: Request, sb_client: AsyncClient = Depends(get_supabase_db)):
    """Handle the OAuth callback, exchange code for tokens, and store tokens for the user in Supabase metadata."""
    code = callback_data.code
    logger.info(f"Handling callback for code (start): {code[:5]}...") # Log start
    try:
        if not code:
            logger.error("Callback received empty/missing code in request body.")
            raise HTTPException(status_code=400, detail="Code parameter is required")
        
        logger.info(f"Attempting token exchange with Bungie for code: {code[:5]}...")
        token_data = oauth_manager.handle_callback(code)
        logger.info(f"Successfully exchanged code for token data.")

        # Extract token info
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in')

        if not all([access_token, refresh_token, expires_in]):
             logger.error("Token exchange response missing required fields.", extra={"token_data": token_data})
             raise HTTPException(status_code=500, detail="Failed to get complete token data from Bungie")

        # Calculate expiry time (store as UTC)
        now_utc = datetime.now(timezone.utc)
        expires_at_utc = now_utc + timedelta(seconds=expires_in)

        # Get Bungie ID using the new access token
        logger.info("Getting Bungie ID for the user...")
        bungie_id = oauth_manager.get_bungie_id(access_token)
        if not bungie_id:
             logger.error("Failed to get Bungie ID using the new access token.")
             raise HTTPException(status_code=500, detail="Failed to verify user identity with Bungie")
        logger.info(f"Retrieved Bungie ID: {bungie_id}")

        # --- Get Supabase Auth UUID from frontend (required) ---
        supabase_uuid = getattr(callback_data, 'supabase_uuid', None)
        if not supabase_uuid:
            logger.error("Supabase UUID not provided by frontend. Cannot continue.")
            raise HTTPException(status_code=400, detail="Supabase UUID is required in the callback. Please ensure the frontend sends it.")
        logger.info(f"Using Supabase UUID from frontend: {supabase_uuid}")

        # --- Store Bungie tokens and Bungie ID in Supabase user metadata ---
        try:
            # Prepare metadata update
            metadata_update = {
                "bungie_id": str(bungie_id),
                "bungie_access_token": access_token,
                "bungie_refresh_token": refresh_token,
                "bungie_token_expires": expires_at_utc.isoformat()
            }
            update_resp = await sb_client.table("users").update({"raw_user_meta_data": metadata_update}).eq("id", supabase_uuid).execute()
            if update_resp.error:
                logger.error(f"Failed to update Supabase user metadata: {update_resp.error}")
                raise HTTPException(status_code=500, detail="Failed to update Supabase user metadata.")
            logger.info(f"Successfully updated Supabase user metadata for UUID {supabase_uuid}")
        except Exception as e:
            logger.error(f"Error updating Supabase user metadata: {e}")
            raise HTTPException(status_code=500, detail="Failed to update Supabase user metadata.")

        # --- Create JWT ---
        jwt_expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        jwt_payload = {
            "sub": supabase_uuid, # Subject (standard claim), use Supabase Auth UUID
            "bng": str(bungie_id), # Custom claim for Bungie ID
            "exp": jwt_expires   # Expiration time (standard claim)
        }
        encoded_jwt = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Generated JWT for user (sub={supabase_uuid}) (Bungie ID {bungie_id})")
        # --- End Create JWT ---

        return {
            "status": "success", 
            "access_token": encoded_jwt, # Send the JWT
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60 # Send JWT expiry in seconds
        }
        # --- End Return JWT ---

    except HTTPException as http_exc: # Log FastAPI exceptions before re-raising
        logger.error(f"HTTPException during auth callback: {http_exc.status_code} - {http_exc.detail}", exc_info=False) # Don't need full trace for expected exceptions
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error in auth_callback for code {code[:5]}...: {e}", exc_info=True) # Log other exceptions
        raise HTTPException(status_code=400, detail=f"Authentication callback failed: {str(e)}")

@app.get("/auth/verify", response_model=UserResponse)
async def verify_token(current_user: SupabaseUser = Depends(get_supabase_user_from_token)):
    """Verify the authentication token (JWT)"""
    return {"status": "ok", "user_uuid": current_user.uuid, "bungie_id": current_user.bungie_id}

# --- Endpoint commented out - Use agent tools instead ---
# @app.get("/catalysts/all", response_model=List[CatalystData])
# async def get_all_catalysts_endpoint(current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db_session)):
#     """(DEPRECATED/NEEDS REFACTOR) Get all catalysts for the authenticated user, using a 5-minute cache."""
#     # This endpoint needs refactoring to use get_catalyst_api_dependency 
#     # and potentially remove its own caching logic if agent service handles it.
#     bungie_id = current_user.bungie_id
#     now = datetime.now(timezone.utc)
#     # ... (old caching and API call logic) ...
#     logger.warning("Accessing deprecated /catalysts/all endpoint.")
#     raise HTTPException(status_code=501, detail="Endpoint /catalysts/all needs refactoring or removal.")

# --- NEW Chat History Endpoints ---

@app.get("/api/conversations", response_model=List[ConversationSchema])
async def list_conversations(
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    db_client: AsyncClient = Depends(get_supabase_db), # <--- Reinstate Depends
    archived: bool = Query(False, description="Set to true to show archived conversations")
):
    """Lists all (optionally archived) conversations for the currently authenticated user."""
    logger.info(f"[API] Using Supabase UUID: {current_user.uuid}")
    user_bungie_id = current_user.uuid
    if not user_bungie_id:
        raise HTTPException(status_code=401, detail="User Bungie ID not found in token")
    
    try:
        # Supabase style query
        # Ensure your ConversationSchema matches the selected fields, especially user_id
        query_builder = db_client.table("conversations").select("id, user_id, title, created_at, updated_at, archived") \
            .eq("user_id", user_bungie_id) \
            .eq("archived", archived) \
            .order("updated_at", desc=True)
        
        response = await query_builder.execute()

        validated_conversations = []
        if response.data:
            for conv_data in response.data:
                # Ensure field names from Supabase match ConversationSchema or adapt here
                # Example: if Supabase has 'user_bungie_id' but Pydantic needs 'user_id', map it.
                # Assuming direct mapping for now or that 'user_id' is the correct field in Supabase.
                validated_conversations.append(ConversationSchema.model_validate(conv_data))
        return validated_conversations
            
    except Exception as e:
        logger.error(f"Error listing conversations for user {user_bungie_id} from Supabase: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations.")

@app.get("/api/conversations/{conversation_id}/messages", response_model=List[ChatMessageSchema])
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db) # <--- Changed to Supabase client
):
    """Gets all messages for a specific conversation from Supabase, verifying ownership."""
    logger.info(f"[API] Using Supabase UUID: {current_user.uuid}")
    user_bungie_id = current_user.uuid # Ensure it's a string for comparison
    if not user_bungie_id:
        raise HTTPException(status_code=401, detail="User Bungie ID not found in token")

    try:
        # First, verify the conversation exists and belongs to the user by trying to fetch it.
        # This also implicitly checks ownership.
        conv_response = await sb_client.table("conversations") \
            .select("id") \
            .eq("id", str(conversation_id)) \
            .eq("user_id", user_bungie_id) \
            .maybe_single() \
            .execute() # <--- Add await

        if not conv_response.data:
            logger.warning(f"Conversation {conversation_id} not found for user {user_bungie_id} in Supabase or user does not have access.")
            raise HTTPException(status_code=404, detail="Conversation not found or access denied")

        # Fetch messages ordered by their index (assuming 'order_index' column exists in Supabase 'messages' table)
        messages_response = await sb_client.table("messages") \
            .select("*") \
            .eq("conversation_id", str(conversation_id)) \
            .order("order_index", desc=False) \
            .execute() # <--- Add await

        validated_messages = []
        if messages_response.data:
            for msg_data in messages_response.data:
                # Ensure field names from Supabase match ChatMessageSchema or adapt here
                # Example: if Supabase has 'created_at' but Pydantic needs 'timestamp', map it.
                # Assuming direct mapping or that ChatMessageSchema is already aligned.
                validated_messages.append(ChatMessageSchema.model_validate(msg_data))
        
        return validated_messages
            
    except Exception as e:
        logger.error(f"Error fetching messages for conversation {conversation_id} for user {user_bungie_id} from Supabase: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch messages for the conversation.")

# --- End NEW Chat History Endpoints ---

# --- NEW Title Generation Function ---

# Initialize OpenAI client globally? Or per request? 
# For background task, creating it inside might be safer/simpler.
# Ensure OPENAI_API_KEY is available
if OPENAI_API_KEY:
    try:
        # Using AsyncOpenAI for async function
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized for title generation.")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
        openai_client = None
else:
    logger.warning("OPENAI_API_KEY not set. Title generation will be disabled.")
    openai_client = None

async def generate_and_save_title(conversation_id: uuid.UUID):
    """Fetches first messages from Supabase, calls OpenAI to generate a title, and saves it to Supabase."""
    logger.info(f"Starting title generation task for conversation {conversation_id} using Supabase.")
    
    # Access the global Supabase client and OpenAI client
    global supabase_client, openai_client # Ensure we are referencing the global instances

    if not openai_client:
        logger.error(f"Cannot generate title for {conversation_id}: OpenAI client not available.")
        return
    if not supabase_client:
        logger.error(f"Cannot generate title for {conversation_id}: Supabase client not available.")
        return

    try:
        # Fetch conversation details to check if title already exists
        conv_details_response = (await supabase_client.table("conversations") # <--- Add await
            .select("id, title, user_id")
            .eq("id", str(conversation_id))
            .maybe_single()
            .execute())

        if not conv_details_response.data:
            logger.error(f"Title gen failed: Conversation {conversation_id} not found in Supabase.")
            return
        if conv_details_response.data.get("title"):
            logger.info(f"Title already exists for conversation {conversation_id} in Supabase. Skipping generation.")
            return
        
        user_bungie_id = conv_details_response.data.get("user_id") # Get user_id for logging/context

        # Fetch first user message (order_index 0, sender 'user') from Supabase
        user_msg_response = (await supabase_client.table("messages") # <--- Add await
            .select("content")
            .eq("conversation_id", str(conversation_id))
            .eq("order_index", 0)
            .eq("sender", "user")
            .maybe_single()
            .execute())

        # Fetch first assistant message (order_index 1, sender 'assistant') from Supabase
        assistant_msg_response = (await supabase_client.table("messages") # <--- Add await
            .select("content")
            .eq("conversation_id", str(conversation_id))
            .eq("order_index", 1)
            .eq("sender", "assistant")
            .maybe_single()
            .execute())

        if not user_msg_response.data or not assistant_msg_response.data:
            logger.warning(f"Could not find first user/assistant message for conv {conversation_id} in Supabase (User: {bool(user_msg_response.data)}, Asst: {bool(assistant_msg_response.data)}). Cannot generate title.")
            return

        user_msg_content = user_msg_response.data["content"]
        assistant_msg_content = assistant_msg_response.data["content"]

        # Construct prompt
        prompt = (
            f"Generate a concise title (5 words maximum, plain text only) for the following conversation start:\n\n"
            f"User: {user_msg_content}\n"
            f"Assistant: {assistant_msg_content}\n\n"
            f"Title:"
        )
        
        logger.info(f"Calling OpenAI for title generation (model: gpt-4o) for conv {conversation_id}")
        try:
            completion = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.5,
                n=1,
                stop=None
            )
            generated_title = completion.choices[0].message.content.strip().strip('\"')
            logger.info(f"Generated title for {conversation_id}: '{generated_title}'")
            
            # Save the title to Supabase
            update_title_response = (await supabase_client.table("conversations") # <--- Add await
                .update({"title": generated_title, "updated_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", str(conversation_id))
                .execute())
            
            if update_title_response.data:
                logger.info(f"Successfully saved title for conversation {conversation_id} to Supabase.")
            else:
                logger.error(f"Failed to save title for conversation {conversation_id} to Supabase. Response: {update_title_response.error}")
            
        except Exception as api_err:
            logger.error(f"OpenAI API error during title generation for conv {conversation_id}: {api_err}", exc_info=True)
            # Do not update Supabase conversation if API failed
            
    except Exception as e:
        logger.error(f"Error in Supabase title generation task for conversation {conversation_id}: {e}", exc_info=True)
        # No explicit rollback needed for Supabase as operations are typically atomic per call

# --- End Title Generation Function ---

# --- REWRITTEN: Chat Endpoint <--- 
@app.post("/api/assistants/chat", response_model=ChatResponse)
async def assistants_chat_endpoint(
    request: Request,
    chat_request: ChatRequest,
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db),
):
    """
    Chat endpoint using the agent service, handling conversation history with Supabase.
    """
    logger.info(f"Chat endpoint running in PID: {os.getpid()}")
    total_start = time.time()
    agent_service_instance = request.app.state.agent_service_instance
    if not agent_service_instance:
        logger.error("Chat request failed: DestinyAgentService not available.")
        raise HTTPException(status_code=503, detail="Chat service is currently unavailable.")

    if not OPENAI_API_KEY:
        logger.error("OpenAI API key missing.")
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    user_message_content = chat_request.messages[-1].content if chat_request.messages else ""
    if not user_message_content:
        raise HTTPException(status_code=400, detail="No message content provided")

    bungie_id = current_user.uuid # This is the Supabase UUID
    requested_conversation_id_str = str(chat_request.conversation_id) if chat_request.conversation_id else None

    # Fetch Bungie access token from Supabase user metadata (optional)
    access_token = None
    try:
        user_resp = await sb_client.table("users").select("raw_user_meta_data").eq("id", bungie_id).maybe_single().execute()
        if user_resp.data and user_resp.data.get("raw_user_meta_data"):
            meta = user_resp.data["raw_user_meta_data"]
            access_token = meta.get("bungie_access_token")
        if not access_token:
            logger.warning(f"Bungie access token missing in Supabase metadata for user {bungie_id}. Proceeding without it.")
            # Do NOT raise an error; allow chat to proceed
    except Exception as e:
        logger.error(f"Error fetching Bungie access token from Supabase metadata: {e}. Proceeding without it.")
        access_token = None

    conversation_history = []
    current_conversation_id_str: Optional[str] = None # Store as string for Supabase
    next_order_index = 0

    agent_start = time.time()
    try:
        # --- Handle Existing vs New Conversation ---
        if requested_conversation_id_str:
            logger.info(f"Attempting to continue existing conversation: {requested_conversation_id_str} for user {bungie_id}")
            # Load existing conversation from Supabase
            conv_response = await sb_client.table("conversations") \
                .select("id, user_id, title, created_at, updated_at, archived") \
                .eq("id", requested_conversation_id_str) \
                .eq("user_id", bungie_id) \
                .maybe_single() \
                .execute()

            if not conv_response.data:
                logger.warning(f"Conversation {requested_conversation_id_str} not found for user {bungie_id} or access denied.")
                raise HTTPException(status_code=404, detail="Conversation not found or access denied")
            
            current_conversation_id_str = str(conv_response.data["id"]) # Ensure we use the UUID as string

            # Load history from Supabase
            messages_response = await sb_client.table("messages") \
                .select("sender, content, order_index") \
                .eq("conversation_id", current_conversation_id_str) \
                .order("order_index", desc=False) \
                .execute()
            
            if messages_response.data:
                for msg_data in messages_response.data:
                    # Map 'sender' to 'role' for agent history
                    conversation_history.append({"role": msg_data["sender"], "content": msg_data["content"]})
                next_order_index = len(messages_response.data)
            logger.info(f"Loaded {len(conversation_history)} messages for conversation {current_conversation_id_str}. Next order_index: {next_order_index}")

        else:
            # Start new conversation in Supabase
            logger.info(f"Starting new conversation for user {bungie_id}")
            new_conv_data = {"user_id": bungie_id, "title": None} # title can be generated later
            insert_response = await sb_client.table("conversations").insert(new_conv_data).execute()
            
            if not insert_response.data:
                logger.error(f"Failed to insert new conversation for user {bungie_id} into Supabase.")
                raise HTTPException(status_code=500, detail="Failed to create new conversation record in Supabase.")
            
            current_conversation_id_str = str(insert_response.data[0]["id"]) # Get new ID
            logger.info(f"Created new conversation with ID: {current_conversation_id_str} in Supabase.")
            next_order_index = 0

        # --- Save User Message to Supabase ---
        user_message_to_save = {
            "conversation_id": current_conversation_id_str,
            "sender": "user", # Use 'sender' as per Supabase schema
            "content": user_message_content,
            "order_index": next_order_index
            # Supabase handles 'created_at' (timestamp) and 'id' (message UUID)
        }
        insert_user_msg_response = await sb_client.table("messages").insert(user_message_to_save).execute()
        if not insert_user_msg_response.data:
            logger.error(f"Failed to save user message for conv {current_conversation_id_str} to Supabase.")
            user_message_id = None
        else:
            logger.info(f"Saved user message (order: {next_order_index}) for conv {current_conversation_id_str} to Supabase.")
            user_message_id = insert_user_msg_response.data[0]["id"]
            next_order_index += 1

        # --- Prepare for Agent Call ---
        logger.info(f"Passing chat request to agent service for user {bungie_id}, conversation {current_conversation_id_str}")
        
        run_result = await agent_service_instance.run_chat(
            prompt=user_message_content,
            access_token=access_token,
            bungie_id=bungie_id,
            history=conversation_history,
            persona=chat_request.persona  # <-- Pass persona to agent
        )
        agent_duration_ms = int((time.time() - agent_start) * 1000)
        await log_api_performance(
            sb_client,
            endpoint="/api/assistants/chat",
            operation="agent_service_run_chat",
            duration_ms=agent_duration_ms,
            user_id=bungie_id,
            conversation_id=current_conversation_id_str,
            message_id=user_message_id,
            extra_data={"status": "success"}
        )
        
        agent_response_content = ""
        if isinstance(run_result, str):
            agent_response_content = run_result
        elif isinstance(run_result, dict) and 'error' in run_result:
            logger.error(f"Agent service returned error dict for conv {current_conversation_id_str}: {run_result['error']}")
            # Update timestamp even if agent errored, as an interaction occurred
            await sb_client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", current_conversation_id_str).execute()
            raise HTTPException(status_code=500, detail=run_result['error'])
        else:
            logger.warning(f"Unexpected result type from agent service for conv {current_conversation_id_str}: {type(run_result)}. Result: {run_result}")
            await sb_client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", current_conversation_id_str).execute()
            raise HTTPException(status_code=500, detail="Agent service generated a response, but its format was unexpected.")

        # --- Save Assistant Message to Supabase ---
        assistant_message_to_save = {
            "conversation_id": current_conversation_id_str,
            "sender": "assistant", # Use 'sender'
            "content": agent_response_content,
            "order_index": next_order_index
        }
        insert_asst_msg_response = await sb_client.table("messages").insert(assistant_message_to_save).execute()
        if not insert_asst_msg_response.data:
            logger.error(f"Failed to save assistant message for conv {current_conversation_id_str} to Supabase.")
        else:
            logger.info(f"Saved assistant message (order: {next_order_index}) for conv {current_conversation_id_str} to Supabase.")
        
        # --- Update Conversation Timestamp in Supabase ---
        # This happens regardless of assistant message save success, as user message was processed.
        update_conv_ts_response = await sb_client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", current_conversation_id_str).execute()
        if not update_conv_ts_response.data:
             logger.error(f"Failed to update timestamp for conversation {current_conversation_id_str} in Supabase.")
        else:
            logger.info(f"Updated timestamp for conversation {current_conversation_id_str} in Supabase.")

        # --- Prepare and Return Response ---
        response_message = ChatMessage(role="assistant", content=agent_response_content)
        
        # Convert string UUID back to UUID type for the response model
        final_conversation_id_uuid = uuid.UUID(current_conversation_id_str)

        # Trigger title generation if it was a new chat and first exchange (next_order_index would be 1 after saving user msg)
        if not chat_request.conversation_id and next_order_index == 1: # User message saved, assistant response is about to be generated
            logger.info(f"Condition met for title generation for new conversation {final_conversation_id_uuid}. Note: title gen uses local DB.")
            asyncio.create_task(generate_and_save_title(final_conversation_id_uuid))
            logger.info(f"Background task for title generation for {final_conversation_id_uuid} scheduled (uses local DB).")

        total_duration_ms = int((time.time() - total_start) * 1000)
        await log_api_performance(
            sb_client,
            endpoint="/api/assistants/chat",
            operation="total_request",
            duration_ms=total_duration_ms,
            user_id=bungie_id,
            conversation_id=current_conversation_id_str,
            message_id=user_message_id,
            extra_data={"status": "success"}
        )
        return ChatResponse(message=response_message, conversation_id=final_conversation_id_uuid)

    except HTTPException as http_exc:
        total_duration_ms = int((time.time() - total_start) * 1000)
        await log_api_performance(
            sb_client,
            endpoint="/api/assistants/chat",
            operation="total_request",
            duration_ms=total_duration_ms,
            user_id=bungie_id,
            conversation_id=current_conversation_id_str,
            message_id=user_message_id,
            extra_data={"status": "error", "error": str(http_exc.detail)}
        )
        raise http_exc
    except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err:
        logger.warning(f"Authentication error in assistants_chat_endpoint for user {bungie_id}, conv {requested_conversation_id_str}: {auth_err}")
        raise auth_err
    except Exception as e:
        total_duration_ms = int((time.time() - total_start) * 1000)
        await log_api_performance(
            sb_client,
            endpoint="/api/assistants/chat",
            operation="total_request",
            duration_ms=total_duration_ms,
            user_id=bungie_id,
            conversation_id=current_conversation_id_str,
            message_id=user_message_id,
            extra_data={"status": "error", "error": str(e)}
        )
        if current_conversation_id_str:
            try:
                await sb_client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}) \
                    .eq("id", current_conversation_id_str).execute()
            except Exception as ts_err:
                logger.error(f"Failed to update timestamp during general error handling for conv {current_conversation_id_str}: {ts_err}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/api/models", response_model=ModelListResponse)
async def get_available_models():
    """Endpoint to fetch available models from OpenAI."""
    local_openai_client = None
    if not OPENAI_API_KEY:
        logger.error("OpenAI API Key is missing. Cannot list models.")
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")
    try:
        # Initialize client (consider moving to dependency injection later for efficiency)
        http_client = httpx.Client(trust_env=False)
        local_openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
        logger.info("OpenAI client initialized for model listing.")
        
        model_list = local_openai_client.models.list()
        # Filter for models typically used for chat? Or just return all?
        # Let's return models containing 'gpt' for now to keep it relevant.
        gpt_models = [ModelInfo(id=model.id) for model in model_list if 'gpt' in model.id.lower()]
        # Sort models (optional, e.g., by name)
        gpt_models.sort(key=lambda m: m.id)

        logger.info(f"Returning {len(gpt_models)} GPT models.")
        return ModelListResponse(models=gpt_models)

    except Exception as e:
        logger.error(f"Error fetching models from OpenAI: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch models from AI provider: {e}")

# Serve Static Files (React Build)
# Make sure this path is correct relative to where you run uvicorn
# If running uvicorn from destiny2_catalysts/, the path should be web-app/frontend/build
static_files_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
logger.info(f"Attempting to serve static files from: {os.path.abspath(static_files_path)}")

if os.path.exists(static_files_path) and os.path.isdir(os.path.join(static_files_path, "static")):
    app.mount("/", StaticFiles(directory=static_files_path, html=True), name="static")
    logger.info("Serving static files from frontend build directory.")
else:
    logger.warning(f"Static files directory not found or invalid: {static_files_path}")
    logger.warning("Frontend will not be served by FastAPI.")

# Optional: Add shutdown event to close manifest DB connection
@app.on_event("shutdown")
def shutdown_event():
    logger.info("Application shutting down...")
    # Add any cleanup logic here if needed
    # supabase_manifest_service.close_db() # Example if supabase_manifest_service held a DB connection
    logger.info("Shutdown complete.")

# --- NEW: Delete Conversation Endpoint ---
@app.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db) # Changed to Supabase client
):
    """Deletes a conversation from Supabase."""
    logger.info(f"Attempting to delete conversation {conversation_id} for user {current_user.uuid}")
    try:
        # Supabase cascade delete should handle messages if configured on the DB via foreign keys.
        delete_result = await (
            sb_client.table("conversations")
            .delete()
            .eq("id", str(conversation_id)) # Ensure UUID is cast to string for query
            .eq("user_id", current_user.uuid)
            .execute()
        )
        
        # Check if any rows were affected. 
        # Depending on Supabase client version & actual API response, .count might be available or data might indicate success.
        # For now, we assume if it doesn't error and user_id matches, it's fine.
        # If delete_result.data is empty and no error, it implies no row matched the criteria (or delete doesn't return data).
        # Add more specific checks if a direct count of deleted items is needed and available from the client.
        logger.info(f"Delete operation for conversation {conversation_id} for user {current_user.uuid} completed. Result: {delete_result}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id} for user {current_user.uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete conversation")

# --- NEW: Archive Conversation Endpoint ---
@app.patch("/api/conversations/{conversation_id}/archive", response_model=ConversationSchema)
async def archive_conversation(
    conversation_id: uuid.UUID,
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db) # Changed to Supabase client
):
    """Archives a conversation by setting its 'archived' status to True."""
    logger.info(f"Attempting to archive conversation {conversation_id} for user {current_user.uuid}")
    try:
        update_result = await (
            sb_client.table("conversations")
            .update({"archived": True, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(conversation_id)) # Ensure UUID is cast to string for query
            .eq("user_id", current_user.uuid)
            .execute()
        )

        if not update_result.data:
            logger.warning(f"Archive failed: Conversation {conversation_id} not found for user {current_user.uuid} or no update occurred.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not authorized to archive")

        return ConversationSchema(**update_result.data[0])

    except HTTPException: # Re-raise HTTPException
        raise
    except Exception as e:
        logger.error(f"Error archiving conversation {conversation_id} for user {current_user.uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not archive conversation")

# --- NEW: Rename Conversation Endpoint ---
# Correctly define RenameConversationRequest using pydantic.BaseModel
# from pydantic import BaseModel # Already imported at the top

class RenameConversationRequest(BaseModel): # Ensure this uses the pydantic.BaseModel imported at file top
    title: str

@app.patch("/api/conversations/{conversation_id}/rename", response_model=ConversationSchema)
async def rename_conversation(
    conversation_id: uuid.UUID,
    req: RenameConversationRequest,
    current_user: SupabaseUser = Depends(get_supabase_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db)
):
    """Renames a conversation (changes its title) in Supabase."""
    logger.info(f"Attempting to rename conversation {conversation_id} for user {current_user.uuid} to '{req.title}'")
    
    if not req.title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty.")

    try:
        update_result = await (
            sb_client.table("conversations")
            .update({"title": req.title, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(conversation_id))
            .eq("user_id", current_user.uuid)
            .execute()
        )

        if not update_result.data:
            logger.warning(f"Rename failed: Conversation {conversation_id} not found for user {current_user.uuid} or no update occurred.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or not authorized to rename")

        return ConversationSchema(**update_result.data[0])

    except HTTPException: # Re-raise HTTPException
        raise
    except Exception as e:
        logger.error(f"Error renaming conversation {conversation_id} for user {current_user.uuid}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not rename conversation")

@app.post("/auth/refresh")
async def refresh_jwt_token(Authorization: str = Header(None), sb_client: AsyncClient = Depends(get_supabase_db)):
    """
    Issue a new JWT if the backend has a valid Bungie refresh token for the user.
    The frontend should call this if it gets a 401 due to JWT expiry.
    """
    logger.info("/auth/refresh called. Attempting to refresh JWT using Supabase refresh token.")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not refresh credentials. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not Authorization or not Authorization.startswith("Bearer "):
        logger.error("No Authorization header or wrong format.")
        raise credentials_exception
    jwt_token = Authorization.split(" ", 1)[1]
    try:
        # Decode JWT ignoring expiry to get user info
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        user_sub: str = payload.get("sub")
        bungie_id: str = payload.get("bng")
        if user_sub is None or bungie_id is None:
            logger.error("JWT missing 'sub' or 'bng' claim.")
            raise credentials_exception
        # Fetch refresh token from Supabase user metadata
        user_resp = await sb_client.table("users").select("raw_user_meta_data").eq("id", user_sub).maybe_single().execute()
        refresh_token = None
        if user_resp.data and user_resp.data.get("raw_user_meta_data"):
            meta = user_resp.data["raw_user_meta_data"]
            refresh_token = meta.get("bungie_refresh_token")
        if not refresh_token:
            logger.error(f"No refresh token stored in Supabase metadata for user {user_sub}. Cannot refresh.")
            raise credentials_exception
        # Refresh Bungie access token if needed
        try:
            new_token_data = oauth_manager.refresh_token(refresh_token)
            access_token = new_token_data["access_token"]
            refresh_token = new_token_data["refresh_token"]
            expires_in = new_token_data["expires_in"]
            now_utc = datetime.now(timezone.utc)
            expires_at_utc = now_utc + timedelta(seconds=expires_in)
            # Update Supabase metadata with new tokens
            metadata_update = {
                "bungie_id": bungie_id,
                "bungie_access_token": access_token,
                "bungie_refresh_token": refresh_token,
                "bungie_token_expires": expires_at_utc.isoformat()
            }
            update_resp = await sb_client.table("users").update({"raw_user_meta_data": metadata_update}).eq("id", user_sub).execute()
            if update_resp.error:
                logger.error(f"Failed to update Supabase user metadata: {update_resp.error}")
                raise credentials_exception
            logger.info(f"Refreshed Bungie access token for user {user_sub} and updated Supabase metadata.")
        except Exception as e:
            logger.error(f"Failed to refresh Bungie token: {e}")
            raise credentials_exception
        # Issue new JWT
        jwt_expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        jwt_payload = {
            "sub": user_sub,
            "bng": str(bungie_id),
            "exp": jwt_expires
        }
        encoded_jwt = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Issued new JWT for user (sub={user_sub}) (Bungie ID {bungie_id}) via /auth/refresh.")
        return {
            "status": "success",
            "access_token": encoded_jwt,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    except ExpiredSignatureError:
        logger.info("JWT expired, but ignoring for refresh.")
        raise credentials_exception
    except JWTError as e:
        logger.error(f"JWTError decoding token in /auth/refresh: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in /auth/refresh: {e}")
        raise credentials_exception

# --- NEW: Supabase Manifest Service ---
async def get_supabase_manifest_service() -> SupabaseManifestService:
    """Dependency to get the Supabase manifest service."""
    global supabase_manifest_service # Ensure we're accessing the global
    if supabase_manifest_service is None:
        logger.error("Supabase Manifest Service accessed before initialization or initialization failed.") # Added logger
        raise HTTPException(status_code=500, detail="Supabase Manifest Service not initialized")
    return supabase_manifest_service

async def get_openai_client_dependency(): # Renamed to avoid conflict
    # ... existing code ...
    if openai_client is None: raise HTTPException(status_code=500, detail="OpenAI client not available")
    return openai_client

# START NEW DEPENDENCIES
async def get_catalyst_api_dependency() -> CatalystAPI:
    """Dependency to get an instance of CatalystAPI using global services."""
    global catalyst_api_instance # Access the globally initialized instance
    if catalyst_api_instance is None:
        logger.error("CatalystAPI instance not initialized during startup.")
        raise HTTPException(status_code=503, detail="Catalyst API service not available.")
    return catalyst_api_instance

async def get_weapon_api_dependency() -> WeaponAPI:
    """Dependency to get an instance of WeaponAPI using global services."""
    global weapon_api_instance # Access the globally initialized instance
    if weapon_api_instance is None:
        logger.error("WeaponAPI instance not initialized during startup.")
        raise HTTPException(status_code=503, detail="Weapon API service not available.")
    return weapon_api_instance
# END NEW DEPENDENCIES

# --- Custom Exception Handlers ---
@app.exception_handler(AuthenticationRequiredError)
async def authentication_required_exception_handler(request: Request, exc: AuthenticationRequiredError):
    logger.warning(f"AuthenticationRequiredError caught: {exc}")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "auth_required", "message": str(exc) or "Authentication required. Please log in via Bungie.net."}
    )

@app.exception_handler(InvalidRefreshTokenError)
async def invalid_refresh_token_exception_handler(request: Request, exc: InvalidRefreshTokenError):
    logger.warning(f"InvalidRefreshTokenError caught: {exc}")
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "invalid_refresh_token", "message": str(exc) or "Invalid refresh token. Please log in again."}
    )

# --- Agent Ask Endpoint ---
from pydantic import BaseModel
from fastapi import Body

class AgentAskRequest(BaseModel):
    query: str
    persona: str | None = None
    bungie_id: str | None = None
    access_token: str | None = None

@app.post("/agent/ask")
async def agent_ask_endpoint(
    req: AgentAskRequest = Body(...)
):
    global agent_service_instance
    if not agent_service_instance:
        raise HTTPException(status_code=503, detail="Agent service not initialized.")
    try:
        result = await agent_service_instance.run_chat(
            prompt=req.query,
            access_token=req.access_token,
            bungie_id=req.bungie_id,
            persona=req.persona,
        )
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/user")
async def get_supabase_user_uuid(current_user: SupabaseUser = Depends(get_supabase_user_from_token)):
    """Returns the Supabase Auth user UUID for the current session/user."""
    user_uuid = current_user.uuid
    logger.info(f"/api/auth/user: Returning Supabase user UUID {user_uuid} for user {getattr(current_user, 'bungie_id', None)}")
    return {"user_uuid": user_uuid}

@app.post("/auth/bungie-callback")
async def bungie_callback_endpoint(callback_data: CallbackData, request: Request):
    """
    Handle Bungie OAuth callback, create/find Supabase user, update metadata, and issue JWT.
    """
    code = callback_data.code
    logger.info(f"[BUNGIE-ONLY] Handling Bungie callback for code: {code[:5]}...")
    try:
        if not code:
            logger.error("Callback received empty/missing code in request body.")
            raise HTTPException(status_code=400, detail="Code parameter is required")
        # Exchange code for Bungie tokens
        token_data = oauth_manager.handle_callback(code)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in')
        if not all([access_token, refresh_token, expires_in]):
            logger.error("Token exchange response missing required fields.", extra={"token_data": token_data})
            raise HTTPException(status_code=500, detail="Failed to get complete token data from Bungie")
        # Get Bungie ID
        bungie_id = oauth_manager.get_bungie_id(access_token)
        if not bungie_id:
            logger.error("Failed to get Bungie ID using the new access token.")
            raise HTTPException(status_code=500, detail="Failed to verify user identity with Bungie")
        logger.info(f"[BUNGIE-ONLY] Retrieved Bungie ID: {bungie_id}")
        # Find or create Supabase user by Bungie ID in metadata
        user_id = None
        # Try to find user by Bungie ID in metadata
        resp = sb_admin.table("profiles").select("*").eq("bungie_id", str(bungie_id)).maybe_single().execute()
        if resp.data:
            user_id = resp.data["id"]
            logger.info(f"[BUNGIE-ONLY] Found existing Supabase user for Bungie ID {bungie_id}: {user_id}")
        else:
            # Create user with fake email
            fake_email = f"{bungie_id}@bungie.local"
            user_resp = sb_admin.auth.admin.create_user({
                "email": fake_email,
                "email_confirm": False,
                "user_metadata": {"bungie_id": str(bungie_id)}
            })
            user_id = user_resp.user.id
            logger.info(f"[BUNGIE-ONLY] Created new Supabase user for Bungie ID {bungie_id}: {user_id}")
        # Update user metadata with Bungie tokens
        metadata_update = {
            "bungie_id": str(bungie_id),
            "bungie_access_token": access_token,
            "bungie_refresh_token": refresh_token,
            "bungie_token_expires": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        }
        sb_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": metadata_update})
        logger.info(f"[BUNGIE-ONLY] Updated Supabase user metadata for {user_id}")
        # Issue a JWT for the user (custom, signed with SECRET_KEY)
        jwt_expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        jwt_payload = {
            "sub": user_id,
            "bng": str(bungie_id),
            "exp": jwt_expires
        }
        encoded_jwt = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"[BUNGIE-ONLY] Issued JWT for user {user_id}")
        return {
            "status": "success",
            "access_token": encoded_jwt,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    except Exception as e:
        logger.error(f"[BUNGIE-ONLY] Error in bungie_callback_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Bungie-only authentication failed: {str(e)}")

@app.get("/api/profile")
async def get_user_profile(current_user: SupabaseUser = Depends(get_supabase_user_from_token)):
    """
    Returns the current user's profile from public.profiles using the admin Supabase client.
    Only accessible with a valid JWT (backend-issued).
    """
    try:
        if not sb_admin:
            logger.error("Supabase admin client not initialized.")
            raise HTTPException(status_code=500, detail="Supabase admin client not available.")
        user_id = current_user.uuid
        resp = sb_admin.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
        if not resp.data:
            logger.warning(f"Profile not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Profile not found.")
        return resp.data
    except Exception as e:
        logger.error(f"Error fetching profile for user {getattr(current_user, 'uuid', None)}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile.")

if __name__ == "__main__":
    import uvicorn
    
    # Get the SSL certificate paths from the current directory
    ssl_certfile = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cert.pem"))
    ssl_keyfile = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "key.pem"))
    
    # Check if the certificate files exist
    if os.path.exists(ssl_certfile) and os.path.exists(ssl_keyfile):
        # Run with HTTPS
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=8000,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile
        )
    else:
        # Fallback to HTTP
        print("SSL certificates not found. Running with HTTP only.")
        uvicorn.run(app, host="0.0.0.0", port=8000) 