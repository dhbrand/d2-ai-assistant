from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Query, Header
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

# Use absolute imports
from web_app.backend.bungie_oauth import OAuthManager, InvalidRefreshTokenError, TokenData # Import TokenData here
from web_app.backend.models import ( # Group imports
    init_db, User, Catalyst, CatalystData, 
    CatalystObjective, Weapon, UserResponse,
    CallbackData, # Add CallbackData
    init_chat_history_db, # <-- Import new init function
    # Add imports for chat history models and session
    Conversation, Message, 
    ConversationSchema, ChatMessageSchema, ConversationCreate, ChatMessageBase,
    ChatHistorySessionLocal 
)
from web_app.backend.catalyst import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.manifest import ManifestManager
from web_app.backend.voice import router as voice_router
from web_app.backend.agent_service import DestinyAgentService

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

# --- Database Setup ---
engine, SessionLocal = init_db(DATABASE_URL)

# --- FastAPI App Instance ---
app = FastAPI()

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

# --- Initialize Managers ---
# Note: Creating global instances like this is simple but might not be ideal
# for scaling or complex dependency management. FastAPI's lifespan events
# or dependency injection patterns are often preferred.
logger.info("Initializing ManifestManager...")
manifest_manager = ManifestManager(api_key=BUNGIE_API_KEY, manifest_dir='./manifest_data')
logger.info("ManifestManager initialized.")

oauth_manager = OAuthManager()

catalyst_api = CatalystAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)

logger.info("Initializing WeaponAPI...")
weapon_api = WeaponAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
logger.info("WeaponAPI initialized.")

# ---> ADDED: Initialize Agent Service <---
logger.info("Initializing DestinyAgentService...")
try:
    agent_service = DestinyAgentService(
        bungie_api_key=BUNGIE_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        manifest_manager=manifest_manager
    )
    logger.info("DestinyAgentService initialized.")
except ValueError as e:
    logger.error(f"Failed to initialize DestinyAgentService: {e}")
    agent_service = None # Set to None if initialization fails
except Exception as e:
    logger.error(f"Unexpected error initializing DestinyAgentService: {e}", exc_info=True)
    agent_service = None

# --- Globals & Setup ---

# --- FastAPI Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Run initialization tasks when the application starts."""
    logger.info("Running application startup tasks...")

    # Initialize the Chat History Database
    try:
        logger.info("Initializing chat history database...")
        init_chat_history_db() # Create chat history tables if they don't exist
        logger.info("Chat history database initialization complete.")
    except Exception as e:
        logger.error(f"Failed to initialize chat history database during startup: {e}", exc_info=True)
        # Decide if the app should proceed without chat history db

    # Optional: Initialize the old catalysts.db if still needed
    # try:
    #     logger.info("Initializing main database (catalysts.db)...")
    #     init_db(DATABASE_URL) 
    #     logger.info("Main database initialization complete.")
    # except Exception as e:
    #     logger.error(f"Failed to initialize main database during startup: {e}", exc_info=True)

    logger.info("Application startup tasks finished.")

# --- Caching Setup ---
CACHE_DURATION = timedelta(minutes=5)
_catalyst_cache: Dict[str, Tuple[datetime, List[CatalystData]]] = {}

WEAPON_CACHE_DURATION = timedelta(minutes=10) # Add weapon cache duration
_weapon_cache: Dict[str, Tuple[datetime, List[Weapon]]] = {} # Add weapon cache dict

# In-memory mapping: user_id -> thread_id (for demo; replace with DB for production)
user_thread_map = defaultdict(str)
user_thread_lock = threading.Lock()

# --- Dependency Functions ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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


# async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
# Update function signature to reflect it's getting the JWT
async def get_current_user_from_token(jwt_token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Dependency to get the current user from a JWT, without calling Bungie for validation."""
    # logger.info("[DEBUG] Entering get_current_user") - Old logging
    logger.info("[DEBUG] Entering get_current_user_from_token")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decode and Validate JWT
    try:
        logger.debug(f"[DEBUG] Decoding JWT: {jwt_token[:10]}...")
        payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub") # Get user ID (subject) from JWT payload
        bungie_id: str = payload.get("bng") # Get Bungie ID from JWT payload
        
        if user_id is None or bungie_id is None:
            logger.error("[DEBUG] JWT missing 'sub' or 'bng' claim.", extra={"payload": payload})
            raise credentials_exception
        
        logger.debug(f"[DEBUG] JWT decoded successfully. User DB ID: {user_id}, Bungie ID: {bungie_id}")
        
    except JWTError as e:
        logger.error(f"[DEBUG] JWTError decoding token: {e}", exc_info=True)
        raise credentials_exception
    except Exception as e: # Catch any other decoding errors
        logger.error(f"[DEBUG] Unexpected error decoding JWT: {e}", exc_info=True)
        raise credentials_exception


    # --- REMOVED BUNGIE VALIDATION CALL ---
    # # 2. Get Bungie ID (REQUIRED to find user) - NO LONGER NEEDED FOR VALIDATION
    # try:
    #     bungie_id = oauth_manager.get_bungie_id(access_token)
    #     if not bungie_id: # Should not happen if get_bungie_id raises correctly
    #          logger.error(f"[DEBUG] get_bungie_id failed unexpectedly without exception for token {access_token[:10]}...")
    #          raise HTTPException(status_code=401, detail="Token validation failed (unexpected)")
    #     logger.debug(f"[DEBUG] Got bungie_id: {bungie_id}")
    # 
    # except requests.exceptions.HTTPError as http_err: # Catch specific HTTP errors from Bungie
    #     status_code = http_err.response.status_code if http_err.response is not None else 500
    #     logger.error(f"[DEBUG] HTTP error {status_code} calling get_bungie_id: {http_err}", exc_info=False)
    #     if 500 <= status_code <= 599: # Check if it's a 5xx server error
    #          raise HTTPException(status_code=503, detail=f"Bungie API unavailable ({status_code})")
    #     else: # Assume other errors (4xx) mean the token is invalid
    #          raise HTTPException(status_code=401, detail=f"Token rejected by Bungie ({status_code})")
    # 
    # except Exception as e: # Catch other errors from get_bungie_id
    #     logger.error(f"[DEBUG] Non-HTTP exception calling get_bungie_id for token {access_token[:10]}... Error: {e}", exc_info=True)
    #     raise HTTPException(status_code=401, detail=f"Token validation failed: {e}")
    # --- END REMOVED BUNGIE VALIDATION CALL ---
        
        
    # 2. Find User in Database using ID from JWT
    user = db.query(User).filter(User.id == int(user_id)).first() # Find by DB primary key
    if not user:
        # This implies the user existed when the JWT was issued but is now gone, 
        # or the JWT is somehow invalid/forged despite passing signature check.
        logger.error(f"[DEBUG] User with DB ID {user_id} (from JWT) not found in DB.")
        raise credentials_exception
        
    # Optional: Double-check Bungie ID matches just in case
    if str(user.bungie_id) != bungie_id:
         logger.error(f"[DEBUG] JWT Bungie ID ({bungie_id}) mismatch with DB Bungie ID ({user.bungie_id}) for user DB ID {user_id}")
         raise credentials_exception

    logger.debug(f"[DEBUG] Found user in DB with ID: {user.id} using JWT claims.")

    # --- SIMPLIFIED/REMOVED REFRESH LOGIC FOR NOW ---
    # The JWT validation handles expiry. Refreshing the *Bungie* token 
    # should ideally happen via a separate refresh endpoint or when a 
    # downstream Bungie API call fails due to an expired *Bungie* token.
    # We still return the user object which contains the *currently stored* Bungie tokens.
    # --- END SIMPLIFIED REFRESH LOGIC ---

    # 3. Return the User object
    logger.debug(f"[DEBUG] Returning user object for ID: {user.id}")
    return user

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
async def handle_auth_callback(callback_data: CallbackData, request: Request, db: Session = Depends(get_db)):
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

@app.get("/catalysts/all", response_model=List[CatalystData])
# Update dependency to use the new function name
async def get_all_catalysts_endpoint(current_user: User = Depends(get_current_user_from_token), db: Session = Depends(get_db), manifest_manager: ManifestManager = Depends(lambda: manifest_manager)):
    """Get all catalysts for the authenticated user, using a 5-minute cache."""
    bungie_id = current_user.bungie_id
    now = datetime.now(timezone.utc)

    # Check cache
    if bungie_id in _catalyst_cache:
        cache_time, cached_data = _catalyst_cache[bungie_id]
        if now - cache_time < CACHE_DURATION:
            logger.info(f"Returning cached catalyst data for user {bungie_id}")
            return cached_data
        else:
            logger.info(f"Cache expired for user {bungie_id}")

    logger.info(f"Fetching fresh catalyst data for user {bungie_id}")
    try:
        # Ensure access token is valid (refresh if needed)
        oauth_manager.refresh_if_needed()
        access_token = oauth_manager.token_data['access_token']
        if not access_token:
            logger.error(f"No access token available for user {bungie_id} in get_all_catalysts")
        catalyst_api_instance = CatalystAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
        catalysts_data = catalyst_api_instance.get_catalysts(access_token=access_token)
        logger.info(f"Retrieved {len(catalysts_data)} catalysts from API")
        processed_catalysts = [CatalystData.model_validate(c) for c in catalysts_data]
        logger.info(f"Successfully processed {len(processed_catalysts)} catalysts")
        _catalyst_cache[bungie_id] = (now, processed_catalysts)
        logger.info(f"Updated cache for user {bungie_id}")
        return processed_catalysts
    except Exception as e:
        logger.error(f"Error fetching catalysts for user {bungie_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch catalyst data: {str(e)}")

@app.get("/weapons/all", response_model=List[Weapon]) # Use Weapon Pydantic model
# Update dependency to use the new function name
async def get_all_weapons_endpoint(current_user: User = Depends(get_current_user_from_token), manifest_manager: ManifestManager = Depends(lambda: manifest_manager)):
    """Endpoint to fetch all weapons for the authenticated user, using a 10-minute cache."""
    bungie_id = current_user.bungie_id
    now = datetime.now(timezone.utc)

    # Check cache
    if bungie_id in _weapon_cache:
        cache_time, cached_data = _weapon_cache[bungie_id]
        if now - cache_time < WEAPON_CACHE_DURATION:
            logger.info(f"Returning cached weapon data for user {bungie_id}")
            return cached_data
        else:
            logger.info(f"Weapon cache expired for user {bungie_id}")

    logger.info(f"Fetching fresh weapon data for user: {bungie_id}")
    
    # Ensure we have a valid access token (refreshed by get_current_user if needed)
    access_token = current_user.access_token 
    if not access_token:
        logger.error(f"No valid access token found for user {current_user.bungie_id} after get_current_user")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    try:
        # Use injected manifest_manager
        weapon_api_instance = WeaponAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
        # 1. Get Membership Info
        logger.info(f"Fetching membership info for user {current_user.bungie_id}")
        membership_info = weapon_api_instance.get_membership_info(access_token)
        if not membership_info:
            logger.error(f"Could not retrieve membership info for user {current_user.bungie_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not find Destiny membership info")
        
        membership_type = membership_info['type']
        membership_id = membership_info['id']
        logger.info(f"Found membership Type: {membership_type}, ID: {membership_id}")

        # 2. Fetch Weapons using WeaponAPI instance
        logger.info(f"Calling weapon_api.get_all_weapons for {membership_type}/{membership_id}")
        weapons = weapon_api_instance.get_all_weapons(
            access_token=access_token,
            membership_type=membership_type,
            destiny_membership_id=membership_id # Correct keyword argument name
        )
        logger.info(f"Successfully fetched {len(weapons)} weapons for user {current_user.bungie_id}")
        
        # Update cache before returning
        _weapon_cache[bungie_id] = (now, weapons)
        logger.info(f"Updated weapon cache for user {bungie_id}")
        
        return weapons
        
    except HTTPException as http_exc: # Re-raise known HTTP exceptions
        raise http_exc 
    except Exception as e:
        logger.error(f"Unexpected error fetching weapons for user {current_user.bungie_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch weapons data")

# --- NEW Chat History Endpoints ---

@app.get("/api/conversations", response_model=List[ConversationSchema])
async def list_conversations(
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_chat_db),
    archived: int = Query(0, description="Set to 1 to show archived conversations")
):
    """Lists all (optionally archived) conversations for the currently authenticated user."""
    user_bungie_id = current_user.bungie_id
    if not user_bungie_id:
        raise HTTPException(status_code=401, detail="User Bungie ID not found in token")
    query = db.query(Conversation).filter(Conversation.user_bungie_id == str(user_bungie_id))
    if archived:
        query = query.filter(Conversation.archived == True)
    else:
        query = query.filter(Conversation.archived == False)
    conversations = query.order_by(Conversation.updated_at.desc()).all()
    return conversations

@app.get("/api/conversations/{conversation_id}/messages", response_model=List[ChatMessageSchema])
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user_from_token),
    db: Session = Depends(get_chat_db) # Use chat history DB session
):
    """Gets all messages for a specific conversation, verifying ownership."""
    user_bungie_id = current_user.bungie_id
    if not user_bungie_id:
        raise HTTPException(status_code=401, detail="User Bungie ID not found in token")

    # First, verify the conversation exists and belongs to the user
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_bungie_id == str(user_bungie_id)
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")

    # Fetch messages ordered by their index
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.order_index.asc())
        .all()
    )
    return messages

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
    """Fetches first messages, calls OpenAI to generate a title, and saves it."""
    logger.info(f"Starting title generation task for conversation {conversation_id}")
    if not openai_client:
        logger.error(f"Cannot generate title for {conversation_id}: OpenAI client not available.")
        return

    db = None # Initialize db to None
    try:
        # Get a new DB session for this task
        db = ChatHistorySessionLocal()
        
        # Fetch first user message (index 0) and first assistant message (index 1)
        user_msg = db.query(Message).filter(
            Message.conversation_id == conversation_id, 
            Message.order_index == 0,
            Message.role == 'user' 
        ).first()
        
        assistant_msg = db.query(Message).filter(
            Message.conversation_id == conversation_id, 
            Message.order_index == 1, 
            Message.role == 'assistant'
        ).first()
        
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

        if not conversation:
            logger.error(f"Title gen failed: Conversation {conversation_id} not found.")
            return
        if conversation.title:
            logger.info(f"Title already exists for conversation {conversation_id}. Skipping generation.")
            return
        if not user_msg or not assistant_msg:
            logger.warning(f"Could not find first user/assistant message for conv {conversation_id}. Cannot generate title.")
            return

        # Construct prompt
        prompt = (
            f"Generate a concise title (5 words maximum, plain text only) for the following conversation start:\n\n"
            f"User: {user_msg.content}\n"
            f"Assistant: {assistant_msg.content}\n\n"
            f"Title:"
        )
        
        logger.info(f"Calling OpenAI for title generation (model: gpt-4o) for conv {conversation_id}")
        try:
            completion = await openai_client.chat.completions.create(
                model="gpt-4o", # <-- Switch to gpt-4o
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20, # Limit tokens for title
                temperature=0.5, # Slightly creative but not too random
                n=1,
                stop=None
            )
            generated_title = completion.choices[0].message.content.strip().strip('"') # Clean up quotes/whitespace
            logger.info(f"Generated title for {conversation_id}: '{generated_title}'")
            
            # Save the title
            conversation.title = generated_title
            db.commit()
            logger.info(f"Successfully saved title for conversation {conversation_id}")
            
        except Exception as api_err:
            # Log API error - could be invalid model, rate limit, etc.
            logger.error(f"OpenAI API error during title generation for conv {conversation_id}: {api_err}", exc_info=True)
            # Optionally try a fallback model here?
            # For now, just log and exit.
            pass # Don't save title if API failed
            
    except Exception as e:
        logger.error(f"Error in title generation task for conversation {conversation_id}: {e}", exc_info=True)
        if db: # Rollback if any other error occurred
             db.rollback()
    finally:
        if db: # Ensure session is closed
            db.close()

# --- End Title Generation Function ---

# --- REWRITTEN: Chat Endpoint <--- 
@app.post("/api/assistants/chat", response_model=ChatResponse)
async def assistants_chat_endpoint(
    request: ChatRequest, 
    current_user: User = Depends(get_current_user_from_token),
    chat_db: Session = Depends(get_chat_db) # Inject chat history DB session
):
    """
    Chat endpoint using the agent service, handling conversation history.
    """
    if not agent_service:
        logger.error("Chat request failed: DestinyAgentService not available.")
        raise HTTPException(status_code=503, detail="Chat service is currently unavailable.")
        
    if not OPENAI_API_KEY:
        logger.error("OpenAI API key missing.")
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    user_message_content = request.messages[-1].content if request.messages else ""
    if not user_message_content:
        raise HTTPException(status_code=400, detail="No message content provided")

    access_token = current_user.access_token
    bungie_id = current_user.bungie_id # Get bungie_id from the user object
    conversation_id = request.conversation_id # Get from request, could be None
    
    if not access_token or not bungie_id:
        logger.error(f"Auth info missing for user {current_user.id} (Token: {'Present' if access_token else 'Missing'}, BungieID: {'Present' if bungie_id else 'Missing'})")
        raise HTTPException(status_code=401, detail="Authentication token or user ID missing")

    conversation_history = []
    current_conversation: Conversation | None = None
    next_order_index = 0

    # --- Handle Existing vs New Conversation ---
    if conversation_id:
        # Load existing conversation and history
        logger.info(f"Continuing existing conversation: {conversation_id}")
        current_conversation = (
            chat_db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_bungie_id == str(bungie_id)
            )
            .first()
        )
        if not current_conversation:
            logger.warning(f"Attempt to access non-existent or unauthorized conversation {conversation_id} by user {bungie_id}")
            raise HTTPException(status_code=404, detail="Conversation not found or access denied")
        
        # Load history (already ordered by relationship/query)
        db_messages = current_conversation.messages 
        conversation_history = [
            {"role": msg.role, "content": msg.content} 
            for msg in db_messages
        ]
        next_order_index = len(db_messages) # Next index is current length

    else:
        # Start new conversation
        logger.info(f"Starting new conversation for user {bungie_id}")
        current_conversation = Conversation(user_bungie_id=str(bungie_id))
        chat_db.add(current_conversation)
        # We need the ID, so flush to get it assigned by the DB/UUID default
        try:
            chat_db.flush()
            conversation_id = current_conversation.id # Get the newly assigned ID
            logger.info(f"Created new conversation with ID: {conversation_id}")
        except Exception as e:
            logger.error(f"Error flushing new conversation for user {bungie_id}: {e}", exc_info=True)
            chat_db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create new conversation record")
        next_order_index = 0 # First message
        
    # --- Save User Message ---
    user_db_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=user_message_content,
        order_index=next_order_index
    )
    chat_db.add(user_db_message)
    next_order_index += 1

    # --- Prepare for Agent Call ---
    # Add current user message to history *before* calling agent
    conversation_history.append({"role": "user", "content": user_message_content})
    
    logger.info(f"Passing chat request to agent service for user {bungie_id}, conversation {conversation_id}")
    
    # --- Call Agent Service (Modify agent_service later to accept history) ---
    # Call the updated run_chat method with history
    run_result = await agent_service.run_chat(
        prompt=user_message_content, # Pass the latest user message as prompt
        access_token=access_token, 
        bungie_id=str(bungie_id),
        history=conversation_history # Pass the constructed history
    )
    
    # --- Process Agent Response ---
    if isinstance(run_result, dict) and 'error' in run_result:
        logger.error(f"Agent service returned error for conv {conversation_id}: {run_result['error']}")
        # Don't commit the user message if agent failed? Or commit anyway?
        # Let's commit the user message but not the failed assistant response.
        try:
             current_conversation.updated_at = datetime.now(timezone.utc) # Update timestamp even on error
             chat_db.commit()
        except Exception as commit_err:
             logger.error(f"Error committing user message after agent error for conv {conversation_id}: {commit_err}", exc_info=True)
             chat_db.rollback()
        raise HTTPException(status_code=500, detail=run_result['error'])
    
    elif hasattr(run_result, 'final_output'): 
        agent_response_content = run_result.final_output
    else:
        logger.warning(f"Unexpected result type from agent service for conv {conversation_id}: {type(run_result)}")
        try:
             current_conversation.updated_at = datetime.now(timezone.utc)
             chat_db.commit()
        except Exception as commit_err:
             logger.error(f"Error committing user message after unexpected agent result for conv {conversation_id}: {commit_err}", exc_info=True)
             chat_db.rollback()
        raise HTTPException(status_code=500, detail="Received unexpected response from agent service.")

    # --- Save Assistant Message ---
    assistant_db_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=agent_response_content,
        order_index=next_order_index # Use the incremented index
    )
    chat_db.add(assistant_db_message)

    # --- Update Conversation Timestamp and Commit ---
    current_conversation.updated_at = datetime.now(timezone.utc)
    next_order_index += 1 # <-- Increment index AFTER adding assistant message
    try:
        chat_db.commit() # Commit user msg, assistant msg, and timestamp update
        logger.info(f"Successfully saved user and assistant messages for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to commit conversation {conversation_id} updates: {e}", exc_info=True)
        chat_db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save conversation history")

    # --- Prepare and Return Response ---
    response_message = ChatMessage(role="assistant", content=agent_response_content)
    
    # Trigger title generation if it was a new chat and first exchange (next_order_index would be 2 after saving assistant msg)
    if not request.conversation_id and next_order_index == 2: # If it was a new chat AND we just saved the first assistant message
        logger.info(f"Condition met for title generation for new conversation {conversation_id}.") # Add specific log
        # Call the async background task
        asyncio.create_task(generate_and_save_title(conversation_id))
        logger.info(f"Background task for title generation for {conversation_id} scheduled.")

    return ChatResponse(message=response_message, conversation_id=conversation_id)

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
    # manifest_manager.close_db() # Example if manifest manager held a DB connection
    logger.info("Shutdown complete.")

app.include_router(voice_router)

# Add a root endpoint for basic check
@app.get("/")
def read_root():
    return {"message": "Destiny 2 Assistant Backend is running."}

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
def refresh_jwt_token(Authorization: str = Header(None), db: Session = Depends(get_db)):
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