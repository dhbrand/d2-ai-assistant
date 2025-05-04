from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
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
from openai import OpenAI
import httpx # Import httpx
import json
import time
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# Use absolute imports
from web_app.backend.bungie_oauth import OAuthManager, InvalidRefreshTokenError, TokenData # Import TokenData here
from web_app.backend.models import ( # Group imports
    init_db, User, Catalyst, CatalystData, 
    CatalystObjective, Weapon, UserResponse,
    CallbackData # Add CallbackData
)
from web_app.backend.catalyst import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.manifest import ManifestManager

# --- Pydantic Models for Chat (Moved Up) ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    token_data: Optional[TokenData] = None # Allow frontend to send token if needed

class ChatResponse(BaseModel):
    message: ChatMessage
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
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # Should match Bungie's expiry if possible, but our JWT has its own life
DATABASE_URL = "sqlite:///./catalysts.db"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Uncomment

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

catalyst_api = CatalystAPI(api_key=BUNGIE_API_KEY)

logger.info("Initializing WeaponAPI...")
weapon_api = WeaponAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
logger.info("WeaponAPI initialized.")

# --- Globals & Setup ---

# --- Caching Setup ---
CACHE_DURATION = timedelta(minutes=5)
_catalyst_cache: Dict[str, Tuple[datetime, List[CatalystData]]] = {}

WEAPON_CACHE_DURATION = timedelta(minutes=10) # Add weapon cache duration
_weapon_cache: Dict[str, Tuple[datetime, List[Weapon]]] = {} # Add weapon cache dict

# --- Dependency Functions ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # Dummy URL, we use /auth/callback

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Dependency to get the current user, handling token refresh if necessary."""
    logger.info("[DEBUG] Entering get_current_user")
    
    # Token is now directly injected by Depends(oauth2_scheme)
    access_token = token 
    logger.debug(f"[DEBUG] Received access token via dependency: {access_token[:10]}...")
    
    # 2. Get Bungie ID (REQUIRED to find user)
    try:
        bungie_id = oauth_manager.get_bungie_id(access_token)
        if not bungie_id: # Should not happen if get_bungie_id raises correctly
             logger.error(f"[DEBUG] get_bungie_id failed unexpectedly without exception for token {access_token[:10]}...")
             raise HTTPException(status_code=401, detail="Token validation failed (unexpected)")
        logger.debug(f"[DEBUG] Got bungie_id: {bungie_id}")

    except requests.exceptions.HTTPError as http_err: # Catch specific HTTP errors from Bungie
        status_code = http_err.response.status_code if http_err.response is not None else 500
        logger.error(f"[DEBUG] HTTP error {status_code} calling get_bungie_id: {http_err}", exc_info=False)
        if 500 <= status_code <= 599: # Check if it's a 5xx server error
             raise HTTPException(status_code=503, detail=f"Bungie API unavailable ({status_code})")
        else: # Assume other errors (4xx) mean the token is invalid
             raise HTTPException(status_code=401, detail=f"Token rejected by Bungie ({status_code})")

    except Exception as e: # Catch other errors from get_bungie_id
        logger.error(f"[DEBUG] Non-HTTP exception calling get_bungie_id for token {access_token[:10]}... Error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail=f"Token validation failed: {e}")
        
    # 3. Find User in Database (Now we definitely have bungie_id)
    user = db.query(User).filter(User.bungie_id == bungie_id).first()
    if not user:
        logger.error(f"[DEBUG] User with bungie_id {bungie_id} not found in DB for a validated token.")
        raise HTTPException(status_code=401, detail="User profile not found. Please login again.")

    logger.debug(f"[DEBUG] Found user in DB with ID: {user.id}")

    # 4. Check Token Expiry and Refresh if Needed
    refresh_needed = False
    if not user.access_token_expires:
        logger.warning(f"[DEBUG] User {user.id} has no token expiry time stored. Assuming refresh needed.")
        refresh_needed = True
    else:
        # Compare expiry (UTC) with current time (UTC), add buffer
        buffer = timedelta(seconds=60)
        expires = user.access_token_expires
        if expires.tzinfo is None:
            # Assume UTC if naive
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= (datetime.now(timezone.utc) + buffer):
            logger.info(f"[DEBUG] Access token for user {user.id} expired or expiring soon. Refresh needed.")
            refresh_needed = True
        else:
            logger.debug(f"[DEBUG] Access token for user {user.id} is still valid.")

    if refresh_needed:
        if not user.refresh_token:
            logger.error(f"[DEBUG] Refresh needed for user {user.id}, but no refresh token stored!")
            raise HTTPException(status_code=401, detail="Authentication expired, please log in again.")
        
        logger.info(f"[DEBUG] Attempting token refresh for user {user.id}...")
        try:
            new_token_data = oauth_manager.refresh_token(user.refresh_token)
            
            # Update user with new tokens
            user.access_token = new_token_data['access_token']
            user.refresh_token = new_token_data['refresh_token'] # Bungie might issue a new refresh token
            new_expires_in = new_token_data['expires_in']
            user.access_token_expires = datetime.now(timezone.utc) + timedelta(seconds=new_expires_in)
            
            db.commit()
            logger.info(f"[DEBUG] Successfully refreshed token for user {user.id}. New expiry: {user.access_token_expires}")
            
            # Update the token the rest of THIS request might try to use
            # This is slightly hacky. A better DI system might be needed long term.
            # We now return the user, API clients should use user.access_token ideally.
            access_token = user.access_token 

        except InvalidRefreshTokenError as ire:
            logger.error(f"[DEBUG] Refresh token for user {user.id} was invalid: {ire}")
            user.access_token = None
            user.refresh_token = None
            user.access_token_expires = None
            db.commit()
            raise HTTPException(status_code=401, detail="Authentication invalid, please log in again.")
        except Exception as e:
            logger.error(f"[DEBUG] Token refresh failed for user {user.id}: {e}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not refresh authentication token.")

    # 5. Return the User object
    # Make sure the user object has the LATEST access token if a refresh happened
    # The code above already updates user.access_token before returning
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

        # --- Save token to file for test script/external use ---
        try:
            token_file_data = {
                'access_token': access_token,
                'refresh_token': refresh_token, # Optional, but useful for debugging
                'expires_in': expires_in,
                'fetched_at': now_utc.timestamp(), # Store fetch time as Unix timestamp
                'bungie_id': bungie_id # Also useful
            }
            with open("token.json", 'w') as f:
                json.dump(token_file_data, f, indent=4)
            logger.info("Successfully wrote token data to token.json")
        except Exception as file_err:
            logger.error(f"Failed to write token data to token.json: {file_err}")
        # --- End save token to file ---

        # Return only access token and expiry to frontend
        return {
            "status": "success", 
            "token_data": {
                "access_token": access_token,
                "expires_in": expires_in
                # DO NOT send refresh_token to frontend
            }
        }

    except HTTPException as http_exc: # Log FastAPI exceptions before re-raising
        logger.error(f"HTTPException during auth callback: {http_exc.status_code} - {http_exc.detail}", exc_info=True)
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error in auth_callback for code {code[:5]}...: {e}", exc_info=True) # Log other exceptions
        db.rollback() # Rollback DB changes on error
        raise HTTPException(status_code=400, detail=f"Authentication callback failed: {str(e)}")

@app.get("/auth/verify", response_model=UserResponse) # Use UserResponse
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify the authentication token"""
    return {"status": "valid", "bungie_id": current_user.bungie_id}

@app.get("/catalysts/all", response_model=List[CatalystData])
async def get_all_catalysts_endpoint(current_user: User = Depends(get_current_user), db: Session = Depends(get_db), manifest_manager: ManifestManager = Depends(lambda: manifest_manager)):
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
        # Get current access token from the authenticated user object
        # The get_current_user dependency ensures this token is valid/refreshed
        access_token = current_user.access_token
        if not access_token:
            # This should ideally not happen if get_current_user worked, but check defensively
            logger.error(f"No access token available for user {bungie_id} in get_all_catalysts")

        # Fetch data from Bungie API via CatalystAPI
        logger.info("Fetching catalysts from Bungie API...")
        # Use injected manifest_manager
        catalyst_api_instance = CatalystAPI(api_key=BUNGIE_API_KEY)
        catalysts_data = catalyst_api_instance.get_catalysts(access_token=access_token)
        logger.info(f"Retrieved {len(catalysts_data)} catalysts from API")

        # Convert raw dicts to Pydantic models (FastAPI does this automatically if returning raw list)
        # We need to do it here if we want to cache the Pydantic models
        processed_catalysts = [CatalystData.model_validate(c) for c in catalysts_data]

        logger.info(f"Successfully processed {len(processed_catalysts)} catalysts")

        # Update cache
        _catalyst_cache[bungie_id] = (now, processed_catalysts)
        logger.info(f"Updated cache for user {bungie_id}")

        return processed_catalysts

    except Exception as e:
        logger.error(f"Error fetching catalysts for user {bungie_id}: {e}", exc_info=True)
        # Consider more specific error handling based on exception type
        raise HTTPException(status_code=500, detail=f"Failed to fetch catalyst data: {str(e)}")

@app.get("/weapons/all", response_model=List[Weapon]) # Use Weapon Pydantic model
async def get_all_weapons_endpoint(current_user: User = Depends(get_current_user), manifest_manager: ManifestManager = Depends(lambda: manifest_manager)):
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

# --- Helper Functions for Data Fetching (for Chat) ---
# Update definitions to accept current_user and manifest_manager
async def get_all_catalysts_for_chat(current_user: User, manifest_manager: ManifestManager) -> List[CatalystData]:
    """Fetches catalyst data for chat context, using cache if valid."""
    # Use bungie_id from the user object for caching
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
        # Get current access token from the authenticated user object
        # The get_current_user dependency ensures this token is valid/refreshed
        access_token = current_user.access_token
        if not access_token:
            # This should ideally not happen if get_current_user worked, but check defensively
            logger.error(f"No access token available for user {bungie_id} in get_all_catalysts_for_chat")

        # Fetch data from Bungie API via CatalystAPI
        logger.info("Fetching catalysts from Bungie API...")
        # Use injected manifest_manager
        catalyst_api_instance = CatalystAPI(api_key=BUNGIE_API_KEY)
        catalysts_data = catalyst_api_instance.get_catalysts(access_token=access_token)
        logger.info(f"Retrieved {len(catalysts_data)} catalysts from API")

        # Convert raw dicts to Pydantic models (FastAPI does this automatically if returning raw list)
        processed_catalysts = [CatalystData.model_validate(c) for c in catalysts_data]

        logger.info(f"Successfully processed {len(processed_catalysts)} catalysts")

        # Update cache
        _catalyst_cache[bungie_id] = (now, processed_catalysts)
        logger.info(f"Updated cache for user {bungie_id}")

        return processed_catalysts

    except Exception as e:
        logger.error(f"Error fetching catalysts for user {bungie_id}: {e}", exc_info=True)
        # Consider more specific error handling based on exception type
        raise HTTPException(status_code=500, detail=f"Failed to fetch catalyst data: {str(e)}")

# Update definitions to accept current_user and manifest_manager
async def get_all_weapons_for_chat(current_user: User, manifest_manager: ManifestManager) -> List[Weapon]:
    """Fetches weapon data for chat context, using cache if valid."""
    # Use bungie_id from the user object for caching
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

@app.post("/api/chat", response_model=ChatResponse)
# Inject manifest_manager via dependency as well
async def chat_endpoint(request: ChatRequest, current_user: User = Depends(get_current_user), manifest_manager: ManifestManager = Depends(lambda: manifest_manager)):
    # --- Initialize OpenAI Client within endpoint (for debugging NameError) ---
    local_openai_client = None
    if not OPENAI_API_KEY:
        logger.error("OpenAI API Key is missing. Cannot initialize client.")
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")
    try:
        # Initialize httpx client without the problematic 'proxies' argument
        http_client = httpx.Client(trust_env=False)
        local_openai_client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
        logger.info("OpenAI client initialized successfully within endpoint (trust_env=False).")
    except Exception as e_init:
        logger.error(f"Failed to initialize OpenAI client within endpoint: {e_init}", exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to initialize AI assistant client")
    # --- End Per-Request Initialization ---

    # Use the locally initialized client
    if not local_openai_client:
        # This condition should technically be unreachable if the try/except above works,
        # but kept for robustness.
        raise HTTPException(status_code=503, detail="OpenAI client could not be initialized")

    user_message = request.messages[-1] # Get the latest user message
    conversation_history = request.messages # Include previous messages if sent

    # --- Fetch Context Data ---
    context_str = "No additional Destiny 2 data available."
    try:
        # Fetch data using the current_user and injected manifest_manager object
        # Call the correctly named helper functions
        logger.info(f"Fetching context data for user {current_user.bungie_id}...")
        weapons = await get_all_weapons_for_chat(current_user, manifest_manager)
        catalysts = await get_all_catalysts_for_chat(current_user, manifest_manager)

        # Format data for the prompt (simple string representation)
        weapon_details = []
        for w in weapons:
            # Format perks list, handle empty list
            perks_str = ", ".join(w.perks) if w.perks else "No specific perks found"
            detail = (
                f"- {w.name} ({w.tier_type} {w.item_type} - {w.item_sub_type}, {w.damage_type} Damage)\n"
                f"  Location: {w.location or 'Unknown'}, Equipped: {w.is_equipped}"
                f"\n  Perks: {perks_str}"
                # Optionally add hash/instance ID:
                # f"\n  Hash: {w.item_hash}, Instance: {w.instance_id or 'N/A'}"
            )
            weapon_details.append(detail)
        weapon_context = "\n\n".join(weapon_details) # Add extra newline between weapons

        catalyst_context = "\n".join([
            f"- {c.name}: {'Complete' if c.complete else 'Incomplete'} ({'/'.join([f'{o.description}: {o.progress}/{o.completion}' for o in c.objectives])})"
            for c in catalysts
        ])

        context_str = (
            f"Here is the user's current Destiny 2 weapon and catalyst information:\n\n"
            f"**Weapons ({len(weapons)}):**\n{weapon_context}\n\n"
            f"**Catalysts ({len(catalysts)}):**\n{catalyst_context}"
        )
        logger.info(f"Generated context string with {len(weapons)} weapons and {len(catalysts)} catalysts for user {current_user.bungie_id}.")

    except HTTPException as e:
        # Log HTTP errors during context fetching but continue
        logger.error(f"Failed to fetch context data for user {current_user.bungie_id} due to HTTPException: {e.detail}")
        context_str = "Could not retrieve current Destiny 2 data. Answer based on general knowledge."
    except Exception as e:
        # Log other unexpected errors during context fetching but continue
        logger.error(f"An unexpected error occurred fetching context data for user {current_user.bungie_id}: {e}", exc_info=True)
        context_str = "An error occurred retrieving current Destiny 2 data. Answer based on general knowledge."

    # --- Prepare messages for OpenAI ---
    system_prompt = ChatMessage(
        role="system",
        content=(
            "You are a helpful assistant knowledgeable about Destiny 2. "
            "Use the provided player inventory information to answer questions accurately. "
            "If the user asks about their weapons, catalysts, or progress, refer to the data below. "
            "If the data is unavailable or doesn't contain the answer, say so explicitly. "
            "Keep your answers concise and relevant to Destiny 2.\n\n"
            f"{context_str}"
        )
    )

    messages_for_api = [system_prompt.model_dump()] + [msg.model_dump() for msg in conversation_history]

    try:
        logger.info(f"Sending {len(messages_for_api)} messages to OpenAI API.")
        # logger.debug(f"Messages for API: {messages_for_api}") # Potentially very verbose

        # Use the local client instance
        chat_completion = local_openai_client.chat.completions.create(
            model="gpt-4o", # Or your preferred model
            messages=messages_for_api,
        )
        response_content = chat_completion.choices[0].message.content
        logger.info("Received response from OpenAI API.")
        # logger.debug(f"OpenAI Response: {response_content}")

        ai_message = ChatMessage(role="assistant", content=response_content or "...") # Ensure content is not None

        return ChatResponse(message=ai_message)

    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}", exc_info=True)
        # Check for specific OpenAI errors if needed (e.g., AuthenticationError)
        if "AuthenticationError" in str(type(e)):
             raise HTTPException(status_code=401, detail=f"OpenAI Authentication Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get response from AI assistant: {e}")

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
    logger.info("Closing manifest database connection...")
    manifest_manager.close()

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