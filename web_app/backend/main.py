from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Query, Header, BackgroundTasks
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
from web_app.backend.models import init_db, User, CatalystData, Weapon, CallbackData, UserResponse, ConversationSchema, ChatMessageSchema, ChatHistorySessionLocal, Conversation, Message # <--- Added missing imports
from sqlalchemy.orm import sessionmaker, Session
from web_app.backend.catalyst import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.agent_service import DestinyAgentService
from .manifest import SupabaseManifestService # Import the new service

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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # <-- Use name from .env

supabase_client: Optional[AsyncClient] = None # <-- Initialize to None
supabase_manifest_service: Optional[SupabaseManifestService] = None # <-- Initialize to None

# --- Database Setup ---
# engine, SessionLocal = init_db(DATABASE_URL) # Commented out if only Supabase is used now
engine = None # Placeholder if engine is needed elsewhere, otherwise remove.

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
agent_service_instance: Optional[DestinyAgentService] = None
catalyst_api_instance: Optional[CatalystAPI] = None
weapon_api_instance: Optional[WeaponAPI] = None
# scheduler = BackgroundScheduler() # Keep scheduler if used
db_session_local: Optional[sessionmaker[Session]] = None 
engine: Optional[any] = None # Add placeholder for engine as it's used in startup global

# --- FastAPI Startup Event --- 
@app.on_event("startup")
async def startup_event():
    """Run initialization tasks when the application starts."""
    logger.info("Running application startup tasks...")
    # Declare all globals that are referenced or assigned to within this function
    global oauth_manager, engine, db_session_local, supabase_client, supabase_manifest_service, openai_client, catalyst_api_instance, weapon_api_instance, agent_service_instance

    # Initialize Supabase Client and Manifest Service FIRST
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            # Use create_async_client for an asynchronous client
            supabase_client = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Supabase ASYNC client initialized in startup.")

            # Initialize SupabaseManifestService (depends on supabase_client)
            supabase_manifest_service = SupabaseManifestService(sb_client=supabase_client)
            logger.info("SupabaseManifestService initialized with ASYNC client in startup.")

        except Exception as e:
            logger.exception(f"Error initializing Supabase client or SupabaseManifestService in startup: {e}")
            # supabase_client and supabase_manifest_service will remain None
    else:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment variables. Supabase services will not be available.")

    # Initialize the old SQLite DB for User/Token storage
    try:
        logger.info(f"Initializing SQLite database at {DATABASE_URL}...")
        # Call init_db, which now returns engine and the configured sessionmaker
        local_engine, configured_session_local = init_db(DATABASE_URL) 
        engine = local_engine # Store engine if needed globally
        db_session_local = configured_session_local # Store the session factory globally
        logger.info("SQLite database initialization complete (tables checked/created, session factory configured).")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database during startup: {e}", exc_info=True)
        # App might not function correctly without user DB

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
    # agent_service_instance is already declared global at the module level and its assignment is handled by the global keyword below
    if openai_client and catalyst_api_instance and weapon_api_instance and supabase_client:
        try:
            logger.info("Attempting to initialize DestinyAgentService...")
            agent_service_instance = DestinyAgentService(
                openai_client=openai_client,
                catalyst_api=catalyst_api_instance,
                weapon_api=weapon_api_instance,
                supabase_client=supabase_client
            )
            logger.info("DestinyAgentService initialized.")
        except Exception as e:
            logger.exception(f"Error initializing DestinyAgentService: {e}")
            agent_service_instance = None
    else:
        missing_deps = []
        if not openai_client: missing_deps.append("OpenAI Client (global)")
        if not catalyst_api_instance: missing_deps.append("CatalystAPI (global)")
        if not weapon_api_instance: missing_deps.append("WeaponAPI (global)")
        if not supabase_client: missing_deps.append("Supabase Client (global)")
        logger.error(f"DestinyAgentService could not be initialized. Missing: {', '.join(missing_deps)}")

    logger.info("Application startup tasks finished.")

# --- Caching Setup ---
CACHE_DURATION = timedelta(minutes=5)
_catalyst_cache: Dict[str, Tuple[datetime, List[CatalystData]]] = {}

WEAPON_CACHE_DURATION = timedelta(minutes=10) # Add weapon cache duration
_weapon_cache: Dict[str, Tuple[datetime, List[Weapon]]] = {}

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

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Dummy URL, we use /auth/callback
# Use the standard scheme but expect the JWT in the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/dummy_token_url") 

# Dependency for getting the current user from JWT
async def get_current_user_from_token(jwt_token: str = Depends(oauth2_scheme), db: Session = Depends(get_db_session)) -> User:
    """Dependency to get the current user from a JWT, fetching user data from DB."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        bungie_id: str = payload.get("bng")
        if user_id is None or bungie_id is None:
            logger.error("JWT missing 'sub' or 'bng' claim.")
            raise credentials_exception
        
        # Fetch user from DB using the injected session `db`
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
             logger.error(f"User with DB ID {user_id} (from JWT) not found in DB.")
             raise credentials_exception
        # Optional: Double-check Bungie ID matches
        if str(user.bungie_id) != bungie_id:
             logger.error(f"JWT Bungie ID ({bungie_id}) mismatch with DB Bungie ID ({user.bungie_id}) for user DB ID {user_id}")
             raise credentials_exception
        
        # TODO: Implement Bungie token refresh logic if needed here or elsewhere
        # based on user.access_token_expires compared to now.
        
        return user
    except JWTError:
        logger.error("JWTError decoding token.", exc_info=True)
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user_from_token: {e}", exc_info=True)
        # Don't raise generic 500, stick to 401 for auth failures
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
async def handle_auth_callback(callback_data: CallbackData, request: Request, db: Session = Depends(get_db_session)):
    """Handle the OAuth callback, exchange code for tokens, and store tokens for the user."""
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

        # Find or create user in DB
        user = db.query(User).filter(User.bungie_id == bungie_id).first()
        
        if user:
            logger.info(f"Updating tokens for existing user ID: {user.id}")
            user.access_token = access_token
            user.refresh_token = refresh_token
            user.access_token_expires = expires_at_utc
        else:
            logger.info(f"Creating new user for Bungie ID: {bungie_id}")
            user = User(
                bungie_id=bungie_id, 
                access_token=access_token, 
                refresh_token=refresh_token, 
                access_token_expires=expires_at_utc
            )
            db.add(user)
        
        db.commit()
        logger.info(f"Successfully stored/updated tokens for user {bungie_id}")

        # --- Create JWT ---
        jwt_expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        # Use the user ID from the database record we just committed
        db.refresh(user) # Ensure we have the ID if it was a new user
        user_id = user.id 
        
        jwt_payload = {
            "sub": str(user_id), # Subject (standard claim), use database user ID
            "bng": str(bungie_id), # Custom claim for Bungie ID
            "exp": jwt_expires   # Expiration time (standard claim)
        }
        
        encoded_jwt = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Generated JWT for user ID {user_id} (Bungie ID {bungie_id})")
        # --- End Create JWT ---

        # --- Return JWT to frontend ---
        # Return only access token and expiry to frontend - OLD RETURN
        # return {
        #     "status": "success", 
        #     "token_data": {
        #         "access_token": access_token,
        #         "expires_in": expires_in
        #         # DO NOT send refresh_token to frontend
        #     }
        # }
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
        db.rollback() # Rollback DB changes on error
        raise HTTPException(status_code=400, detail=f"Authentication callback failed: {str(e)}")

@app.get("/auth/verify", response_model=UserResponse) # Use UserResponse
# Update dependency to use the new function name
async def verify_token(current_user: User = Depends(get_current_user_from_token)):
    """Verify the authentication token (JWT)"""
    # Keep current_user parameter name for consistency in endpoint signature if desired
    return {"status": "ok", "bungie_id": current_user.bungie_id}

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
    current_user: User = Depends(get_current_user_from_token),
    db_client: AsyncClient = Depends(get_supabase_db), # <--- Reinstate Depends
    archived: bool = Query(False, description="Set to true to show archived conversations")
):
    """Lists all (optionally archived) conversations for the currently authenticated user."""
    user_bungie_id = str(current_user.bungie_id)
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
    current_user: User = Depends(get_current_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db) # <--- Changed to Supabase client
):
    """Gets all messages for a specific conversation from Supabase, verifying ownership."""
    user_bungie_id = str(current_user.bungie_id) # Ensure it's a string for comparison
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
    request: ChatRequest,
    current_user: User = Depends(get_current_user_from_token),
    sb_client: AsyncClient = Depends(get_supabase_db) # <--- Changed to Supabase client
):
    """
    Chat endpoint using the agent service, handling conversation history with Supabase.
    """
    if not agent_service_instance:
        logger.error("Chat request failed: DestinyAgentService not available.")
        raise HTTPException(status_code=503, detail="Chat service is currently unavailable.")

    if not OPENAI_API_KEY:
        logger.error("OpenAI API key missing.")
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    user_message_content = request.messages[-1].content if request.messages else ""
    if not user_message_content:
        raise HTTPException(status_code=400, detail="No message content provided")

    access_token = current_user.access_token
    bungie_id = str(current_user.bungie_id) # Ensure string
    requested_conversation_id_str = str(request.conversation_id) if request.conversation_id else None

    if not access_token or not bungie_id:
        logger.error(f"Auth info missing for user {current_user.id}")
        raise HTTPException(status_code=401, detail="Authentication token or user ID missing")

    conversation_history = []
    current_conversation_id_str: Optional[str] = None # Store as string for Supabase
    next_order_index = 0

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
                .execute() # <--- Add await

            if not conv_response.data:
                logger.warning(f"Conversation {requested_conversation_id_str} not found for user {bungie_id} or access denied.")
                raise HTTPException(status_code=404, detail="Conversation not found or access denied")
            
            current_conversation_id_str = str(conv_response.data["id"]) # Ensure we use the UUID as string

            # Load history from Supabase
            messages_response = await sb_client.table("messages") \
                .select("sender, content, order_index") \
                .eq("conversation_id", current_conversation_id_str) \
                .order("order_index", desc=False) \
                .execute() # <--- Add await
            
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
            insert_response = await sb_client.table("conversations").insert(new_conv_data).execute() # <--- Add await
            
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
        insert_user_msg_response = await sb_client.table("messages").insert(user_message_to_save).execute() # <--- Add await
        if not insert_user_msg_response.data:
            logger.error(f"Failed to save user message for conv {current_conversation_id_str} to Supabase.")
            # Not raising HTTPException here to allow agent to still respond if possible, but log it.
        else:
            logger.info(f"Saved user message (order: {next_order_index}) for conv {current_conversation_id_str} to Supabase.")
            next_order_index += 1

        # --- Prepare for Agent Call ---
        conversation_history.append({"role": "user", "content": user_message_content})
        
        logger.info(f"Passing chat request to agent service for user {bungie_id}, conversation {current_conversation_id_str}")
        
        run_result = await agent_service_instance.run_chat(
            prompt=user_message_content,
            access_token=access_token,
            bungie_id=bungie_id,
            history=conversation_history
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
        insert_asst_msg_response = await sb_client.table("messages").insert(assistant_message_to_save).execute() # <--- Add await
        if not insert_asst_msg_response.data:
            logger.error(f"Failed to save assistant message for conv {current_conversation_id_str} to Supabase.")
        else:
            logger.info(f"Saved assistant message (order: {next_order_index}) for conv {current_conversation_id_str} to Supabase.")
        
        # --- Update Conversation Timestamp in Supabase ---
        # This happens regardless of assistant message save success, as user message was processed.
        update_conv_ts_response = await sb_client.table("conversations").update({"updated_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", current_conversation_id_str).execute() # <--- Add await
        if not update_conv_ts_response.data:
             logger.error(f"Failed to update timestamp for conversation {current_conversation_id_str} in Supabase.")
        else:
            logger.info(f"Updated timestamp for conversation {current_conversation_id_str} in Supabase.")

        # --- Prepare and Return Response ---
        response_message = ChatMessage(role="assistant", content=agent_response_content)
        
        # Convert string UUID back to UUID type for the response model
        final_conversation_id_uuid = uuid.UUID(current_conversation_id_str)

        # Trigger title generation if it was a new chat and first exchange (next_order_index would be 1 after saving user msg)
        if not request.conversation_id and next_order_index == 1: # User message saved, assistant response is about to be generated
            # The generate_and_save_title function still uses local DB. This needs to be addressed separately.
            # For now, it might fail or operate on a different data source if not updated.
            logger.info(f"Condition met for title generation for new conversation {final_conversation_id_uuid}. Note: title gen uses local DB.")
            asyncio.create_task(generate_and_save_title(final_conversation_id_uuid))
            logger.info(f"Background task for title generation for {final_conversation_id_uuid} scheduled (uses local DB).")

        return ChatResponse(message=response_message, conversation_id=final_conversation_id_uuid)

    except HTTPException as http_exc:
        logger.error(f"HTTPException in assistants_chat_endpoint for user {bungie_id}, conv {requested_conversation_id_str}: {http_exc.status_code} - {http_exc.detail}", exc_info=False)
        raise http_exc
    except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH AUTH ERRORS SPECIFICALLY
        logger.warning(f"Authentication error in assistants_chat_endpoint for user {bungie_id}, conv {requested_conversation_id_str}: {auth_err}")
        raise auth_err # Re-raise to be caught by the app-level exception handlers
    except Exception as e:
        logger.error(f"Unexpected error in assistants_chat_endpoint for user {bungie_id}, conv {requested_conversation_id_str}: {e}", exc_info=True)
        # Attempt to update timestamp on generic error if we have a conversation ID
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
@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_chat_db)
):
    """Deletes a conversation and all its messages."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_bungie_id == str(current_user.bungie_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.delete(conv)
    db.commit()
    return {"status": "deleted"}

# --- NEW: Archive Conversation Endpoint ---
@app.patch("/api/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_chat_db)
):
    """Archives a conversation (hides from default list)."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_bungie_id == str(current_user.bungie_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    conv.archived = True
    db.commit()
    return {"status": "archived"}

# --- NEW: Rename Conversation Endpoint ---
from pydantic import BaseModel as PydanticBaseModel
class RenameConversationRequest(PydanticBaseModel):
    title: str

@app.patch("/api/conversations/{conversation_id}/rename")
async def rename_conversation(
    conversation_id: uuid.UUID,
    req: RenameConversationRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_chat_db)
):
    """Renames a conversation (changes its title)."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_bungie_id == str(current_user.bungie_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    conv.title = req.title
    db.commit()
    return {"status": "renamed", "title": req.title}

@app.post("/auth/refresh")
def refresh_jwt_token(Authorization: str = Header(None), db: Session = Depends(get_db_session)):
    """
    Issue a new JWT if the backend has a valid Bungie refresh token for the user.
    The frontend should call this if it gets a 401 due to JWT expiry.
    """
    logger.info("/auth/refresh called. Attempting to refresh JWT using backend refresh token.")
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
        user_id: str = payload.get("sub")
        bungie_id: str = payload.get("bng")
        if user_id is None or bungie_id is None:
            logger.error("JWT missing 'sub' or 'bng' claim.")
            raise credentials_exception
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            logger.error(f"User with DB ID {user_id} not found in DB.")
            raise credentials_exception
        if str(user.bungie_id) != bungie_id:
            logger.error(f"JWT Bungie ID ({bungie_id}) mismatch with DB Bungie ID ({user.bungie_id}) for user DB ID {user_id}")
            raise credentials_exception
        # Check for refresh token
        if not user.refresh_token:
            logger.error("No refresh token stored for user. Cannot refresh.")
            raise credentials_exception
        # Refresh Bungie access token if needed
        try:
            new_token_data = oauth_manager.refresh_token(user.refresh_token)
            user.access_token = new_token_data["access_token"]
            user.refresh_token = new_token_data["refresh_token"]
            expires_in = new_token_data["expires_in"]
            now_utc = datetime.now(timezone.utc)
            user.access_token_expires = now_utc + timedelta(seconds=expires_in)
            db.commit()
            logger.info(f"Refreshed Bungie access token for user {user_id}.")
        except Exception as e:
            logger.error(f"Failed to refresh Bungie token: {e}")
            raise credentials_exception
        # Issue new JWT
        jwt_expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        jwt_payload = {
            "sub": str(user.id),
            "bng": str(user.bungie_id),
            "exp": jwt_expires
        }
        encoded_jwt = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Issued new JWT for user {user_id} (Bungie ID {bungie_id}) via /auth/refresh.")
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