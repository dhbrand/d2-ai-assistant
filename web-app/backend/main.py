from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
from bungie_oauth import OAuthManager

# Load environment variables
load_dotenv()

app = FastAPI(title="Destiny 2 Catalyst Tracker API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OAuth manager
oauth_manager = OAuthManager()

class Catalyst(BaseModel):
    recordHash: str
    name: str
    description: str
    weaponType: str
    objectives: List[dict]
    complete: bool
    progress: float

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
async def auth_callback(code: str):
    """Handle the OAuth callback and exchange code for tokens"""
    try:
        token_data = oauth_manager.handle_callback(code)
        return {"status": "success", "token_data": token_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/catalysts", response_model=List[Catalyst])
async def get_catalysts(token: str = Depends(oauth_manager.get_headers)):
    """Get all catalysts for the authenticated user"""
    try:
        # Use the existing CatalystAPI logic here
        # This is a placeholder - we'll implement the full logic
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 