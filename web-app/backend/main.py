from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import requests
from bungie_oauth import OAuthManager, InvalidRefreshTokenError
from models import init_db, User, Catalyst
from sqlalchemy.orm import Session
from catalyst import CatalystAPI
from weapon_api import WeaponAPI
import logging
from enum import Enum
from typing import Literal
import ssl

# Load environment variables
load_dotenv()

app = FastAPI(title="Destiny 2 Catalyst Tracker API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:3000"],  # React dev server with HTTPS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database - get the factory from the function call
engine, SessionLocal = init_db()

# Dependency to get DB session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize OAuth manager
oauth_manager = OAuthManager()
# Get API Key - Assumes it's the same as BUNGIE_CLIENT_SECRET used by OAuthManager
# If you have a separate BUNGIE_API_KEY in .env, use that instead.
# api_key = os.getenv("BUNGIE_API_KEY") or oauth_manager.api_key # Ensure API key is available
api_key = oauth_manager.api_key # Assuming OAuthManager has the key stored
if not api_key:
    raise ValueError("BUNGIE_API_KEY is required for API clients")

logger = logging.getLogger(__name__)

class CatalystBase(BaseModel):
    recordHash: str = Field(alias='record_hash')
    name: str
    description: str
    weaponType: str = Field(alias='weapon_type')
    objectives: List[dict]
    complete: bool
    progress: float

    class Config:
        orm_mode = True
        populate_by_name = True
        from_attributes = True

class CatalystResponse(CatalystBase):
    id: int

class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

class WeaponResponse(BaseModel):
    id: Optional[int] = None
    item_hash: str
    instance_id: Optional[str] = None
    name: str
    description: str
    icon_url: str
    screenshot_url: Optional[str] = None
    tier_type: int
    item_type: int
    item_sub_type: int
    damage_type: Optional[int] = None
    damage_type_name: Optional[str] = None
    ammo_type: Optional[int] = None
    stats: Optional[Dict[str, Any]] = None
    perks: Optional[List[Dict[str, Any]]] = None
    is_equipped: Optional[bool] = None
    is_in_vault: Optional[bool] = None
    is_favorite: Optional[bool] = None
    
    class Config:
        orm_mode = True
        from_attributes = True

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
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

@app.get("/")
async def root():
    return {"message": "Destiny 2 Catalyst Tracker API"}

@app.get("/auth/url")
async def get_auth_url():
    """Get the Bungie OAuth authorization URL"""
    try:
        auth_url = oauth_manager.get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    """Handle the OAuth callback, exchange code for tokens, and store tokens for the user."""
    try:
        data = await request.json()
        code = data.get('code')
        if not code:
            raise HTTPException(status_code=400, detail="Code parameter is required")
        
        logger.info(f"Received auth code, exchanging for tokens...")
        token_data = oauth_manager.handle_callback(code)
        logger.info(f"Successfully exchanged code for token data.")

        # Extract token info
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in')

        if not all([access_token, refresh_token, expires_in]):
             logger.error("Token exchange response missing required fields.")
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

        # Return only access token and expiry to frontend
        return {
            "status": "success", 
            "token_data": {
                "access_token": access_token,
                "expires_in": expires_in
                # DO NOT send refresh_token to frontend
            }
        }

    except Exception as e:
        logger.error(f"Error in auth_callback: {e}", exc_info=True)
        db.rollback() # Rollback DB changes on error
        # Convert specific exceptions or provide generic error
        if isinstance(e, HTTPException):
            raise # Re-raise FastAPI exceptions
        raise HTTPException(status_code=400, detail=f"Authentication callback failed: {str(e)}")

@app.get("/auth/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify the authentication token"""
    return {"status": "valid", "bungie_id": current_user.bungie_id}

@app.get("/catalysts", response_model=List[CatalystResponse])
async def get_catalysts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all catalysts for the authenticated user"""
    try:
        # Initialize CatalystAPI with API Key
        logger.info("Initializing CatalystAPI...")
        catalyst_api = CatalystAPI(api_key=api_key)
        
        # Get current access token from the authenticated user object
        access_token = current_user.access_token
        if not access_token:
             # This shouldn't happen if get_current_user succeeded, but check defensively
             logger.error(f"No access token found for user {current_user.id} after auth check.")
             raise HTTPException(status_code=401, detail="Missing access token for request.")

        # Fetch catalysts from Bungie API, passing the token
        logger.info("Fetching catalysts from Bungie API...")
        catalysts_data = catalyst_api.get_catalysts(access_token=access_token)
        logger.info(f"Retrieved {len(catalysts_data)} catalysts from API")
        
        # Update database with new catalyst data
        updated_catalysts = []
        for catalyst_data in catalysts_data:
            try:
                logger.debug(f"Processing catalyst: {catalyst_data.get('name', 'Unknown')}")
                
                # Debug the structure of a catalyst
                if len(updated_catalysts) == 0:
                    logger.debug(f"First catalyst data: {catalyst_data}")
                
                catalyst = db.query(Catalyst).filter(
                    Catalyst.record_hash == str(catalyst_data['recordHash']),
                    Catalyst.user_id == current_user.id
                ).first()
                
                if not catalyst:
                    logger.debug(f"Creating new catalyst entry for {catalyst_data['name']}")
                    catalyst = Catalyst(
                        user_id=current_user.id,
                        record_hash=str(catalyst_data['recordHash']),
                        name=catalyst_data['name'],
                        description=catalyst_data['description'],
                        weapon_type=catalyst_data.get('weaponType', 'Unknown'),
                        objectives=catalyst_data['objectives'],
                        complete=catalyst_data.get('complete', False),
                        progress=catalyst_data.get('progress', 0.0)
                    )
                    db.add(catalyst)
                else:
                    logger.debug(f"Updating existing catalyst entry for {catalyst_data['name']}")
                    # Update existing catalyst
                    catalyst.name = catalyst_data['name']
                    catalyst.description = catalyst_data['description']
                    catalyst.weapon_type = catalyst_data.get('weaponType', 'Unknown')
                    catalyst.objectives = catalyst_data['objectives']
                    catalyst.complete = catalyst_data.get('complete', False)
                    catalyst.progress = catalyst_data.get('progress', 0.0)
                
                updated_catalysts.append(catalyst)
            except Exception as inner_e:
                logger.error(f"Error processing individual catalyst: {inner_e}", exc_info=True)
                # Continue processing other catalysts instead of failing
                continue
        
        db.commit()
        logger.info(f"Successfully processed {len(updated_catalysts)} catalysts")
        return updated_catalysts
        
    except Exception as e:
        logger.error(f"Error in get_catalysts: {e}", exc_info=True)
        # db.rollback() # Optionally rollback on error
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/weapons/all", response_model=List[WeaponResponse])
async def get_all_user_weapons(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all weapons for the authenticated user (characters and vault)."""
    try:
        # Initialize WeaponAPI with API Key
        weapon_api = WeaponAPI(api_key=api_key)

        # Get current access token from the authenticated user object
        access_token = current_user.access_token
        if not access_token:
             logger.error(f"No access token found for user {current_user.id} after auth check.")
             raise HTTPException(status_code=401, detail="Missing access token for request.")
        
        # Get membership info, passing the token
        membership = weapon_api.get_membership_info(access_token=access_token)
        if not membership:
            raise HTTPException(status_code=500, detail="Failed to get membership info")
        
        logger.info("Fetching all weapon data...")
        # Fetch weapon data, passing the token
        weapons_data = weapon_api.get_all_weapons(
            access_token=access_token,
            membership_type=membership['type'], 
            membership_id=membership['id']
        )
        logger.info(f"Retrieved weapon data (processing pending): {len(weapons_data)}")
        
        return weapons_data 
        
    except Exception as e:
        logger.error(f"Error in get_all_user_weapons: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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