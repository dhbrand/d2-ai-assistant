from flask import Flask, render_template, redirect, request, session, url_for
from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
import json
import urllib.parse
import secrets
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Enable template debugging
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['EXPLAIN_TEMPLATE_LOADING'] = True

# Bungie API Configuration
BUNGIE_API_ROOT = "https://www.bungie.net/Platform"
BUNGIE_AUTH_URL = "https://www.bungie.net/en/OAuth/Authorize"
BUNGIE_TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
BUNGIE_CLIENT_ID = os.getenv("BUNGIE_CLIENT_ID")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")

logger.debug(f"BUNGIE_CLIENT_ID set: {'Yes' if BUNGIE_CLIENT_ID else 'No'}")
logger.debug(f"BUNGIE_API_KEY set: {'Yes' if BUNGIE_API_KEY else 'No'}")

def get_headers():
    headers = {
        "X-API-Key": BUNGIE_API_KEY
    }
    if "access_token" in session:
        headers["Authorization"] = f"Bearer {session['access_token']}"
    return headers

@app.route("/")
def index():
    logger.debug("Index route accessed")
    logger.debug(f"Session contains access_token: {'Yes' if 'access_token' in session else 'No'}")
    
    try:
        if "access_token" not in session:
            logger.debug("User not authenticated, rendering login page")
            return render_template("index.html", authenticated=False)
        
        logger.debug("Getting membership data")
        membership_data = get_membership_data()
        logger.debug("Getting catalysts")
        catalysts = get_catalysts(membership_data)
        logger.debug(f"Found {len(catalysts)} catalysts")
        return render_template("index.html", authenticated=True, catalysts=catalysts)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        # Return a more detailed error in debug mode
        if app.debug:
            return f"Error: {str(e)}", 500
        return render_template("index.html", authenticated=True, error="Failed to load catalysts")

@app.route("/login")
def login():
    # Generate and store state parameter for security
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    
    params = {
        "client_id": BUNGIE_CLIENT_ID,
        "response_type": "code",
        "state": state
    }
    auth_url = f"{BUNGIE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route("/callback")
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid state parameter", 400
    
    code = request.args.get("code")
    if not code:
        return "No authorization code received", 400

    # Exchange code for access token
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": BUNGIE_CLIENT_ID
    }
    
    headers = {
        "X-API-Key": BUNGIE_API_KEY
    }
    
    response = requests.post(BUNGIE_TOKEN_URL, data=token_data, headers=headers)
    if response.status_code != 200:
        return "Failed to get access token", 400
    
    token_info = response.json()
    session["access_token"] = token_info["access_token"]
    session["refresh_token"] = token_info["refresh_token"]
    session["token_expiry"] = datetime.now() + timedelta(seconds=token_info["expires_in"])
    
    return redirect(url_for("index"))

def get_membership_data():
    response = requests.get(
        f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/",
        headers=get_headers()
    )
    data = response.json()
    return data["Response"]

def get_catalysts(membership_data):
    # Get the first available membership type and ID
    destiny_membership = membership_data["destinyMemberships"][0]
    membership_type = destiny_membership["membershipType"]
    membership_id = destiny_membership["membershipId"]
    
    # Get character IDs
    profile_response = requests.get(
        f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/",
        headers=get_headers(),
        params={
            "components": "200,102"  # Characters and Inventory components
        }
    )
    profile_data = profile_response.json()["Response"]
    
    catalysts = []
    
    # Get catalyst data from inventory
    if "profileInventory" in profile_data:
        inventory_items = profile_data["profileInventory"]["data"]["items"]
        for item in inventory_items:
            # Check if item is a catalyst
            item_response = requests.get(
                f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/Item/{item['itemInstanceId']}",
                headers=get_headers(),
                params={
                    "components": "300,307"  # Item details and objectives
                }
            )
            item_data = item_response.json()["Response"]
            
            # Check if item has objectives (catalysts do)
            if "objectives" in item_data and item_data["objectives"]["data"]:
                objectives = item_data["objectives"]["data"]["objectives"]
                # Filter for catalyst objectives
                if any(obj.get("complete", False) is not None for obj in objectives):
                    catalyst_info = {
                        "name": item_data.get("displayProperties", {}).get("name", "Unknown Catalyst"),
                        "icon": f"https://www.bungie.net{item_data.get('displayProperties', {}).get('icon', '')}",
                        "progress": calculate_progress(objectives),
                        "objective": get_objective_description(objectives)
                    }
                    catalysts.append(catalyst_info)
    
    return catalysts

def calculate_progress(objectives):
    if not objectives:
        return 0
    
    total_progress = 0
    for obj in objectives:
        if obj.get("completionValue", 0) > 0:
            progress = (obj.get("progress", 0) / obj.get("completionValue", 1)) * 100
            total_progress += progress
    
    return min(round(total_progress / len(objectives), 1), 100)

def get_objective_description(objectives):
    if not objectives:
        return "No objectives found"
    
    # Return the first objective's description
    return objectives[0].get("progressDescription", "Complete catalyst objectives")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route('/test')
def test():
    return "Hello! The server is working!"

if __name__ == "__main__":
    # Use port 8080 and listen on all interfaces
    port = 8080
    logger.info(f"Starting server on port {port}")
    app.run(debug=True, port=port, host='0.0.0.0') 