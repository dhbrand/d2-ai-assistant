from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import List, Optional
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
from bungie_oauth import OAuthManager
from models import init_db, User, Catalyst
from sqlalchemy.orm import Session
from catalyst import CatalystAPI
import logging

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

def get_current_user(token_header: dict = Depends(oauth_manager.get_headers), db: Session = Depends(get_db)) -> User:
    logger.info("[DEBUG] Entering get_current_user")
    try:
        logger.info(f"[DEBUG] Received token_header: {token_header}")
        if not isinstance(token_header, dict) or 'Authorization' not in token_header:
             logger.error("[DEBUG] Invalid token header format received from get_headers")
             raise ValueError("Invalid token header format")
             
        auth_header = token_header['Authorization']
        if not auth_header.startswith("Bearer "):
             logger.error("[DEBUG] Authorization header missing 'Bearer ' prefix")
             raise ValueError("Invalid Bearer token format")
             
        token = auth_header.split(" ")[1]
        logger.info(f"[DEBUG] Extracted token: {token[:10]}...")
        
        logger.info("[DEBUG] Calling oauth_manager.get_bungie_id")
        bungie_id = oauth_manager.get_bungie_id(token)
        logger.info(f"[DEBUG] Got bungie_id: {bungie_id}")
        
        # Use the injected session 'db' instead of 'session'
        user = db.query(User).filter(User.bungie_id == bungie_id).first()
        
        if not user:
            logger.info(f"[DEBUG] User with bungie_id {bungie_id} not found in DB. Creating new user.")
            new_user = User(bungie_id=bungie_id, access_token=token) # Store token if needed
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            logger.info(f"[DEBUG] Created new user with ID: {new_user.id}")
            return new_user
        else:
             logger.info(f"[DEBUG] Found user in DB with ID: {user.id}")
             # Optionally update the access token
             # user.access_token = token
             # db.commit()
             return user
             
    except Exception as e:
        logger.error(f"[DEBUG] Exception in get_current_user: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid authentication")

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
async def auth_callback(request: Request):
    """Handle the OAuth callback and exchange code for tokens"""
    try:
        data = await request.json()
        code = data.get('code')
        if not code:
            raise HTTPException(status_code=400, detail="Code parameter is required")
        
        token_data = oauth_manager.handle_callback(code)
        return {"status": "success", "token_data": token_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/auth/verify")
async def verify_token(current_user: User = Depends(get_current_user)):
    """Verify the authentication token"""
    return {"status": "valid", "bungie_id": current_user.bungie_id}

@app.get("/catalysts", response_model=List[CatalystResponse])
async def get_catalysts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all catalysts for the authenticated user"""
    try:
        # Initialize CatalystAPI with the user's token
        logger.info("Initializing CatalystAPI...")
        catalyst_api = CatalystAPI(oauth_manager)
        
        # Fetch catalysts from Bungie API
        logger.info("Fetching catalysts from Bungie API...")
        catalysts_data = catalyst_api.get_catalysts()
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