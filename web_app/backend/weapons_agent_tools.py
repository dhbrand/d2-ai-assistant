from langchain.tools import Tool
from typing import List, Dict, Optional, Any, Union
import pandas as pd
import difflib
import re
import os
import asyncio
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Async tool to fetch all weapons for a user from Supabase
async def get_user_weapons_backend(user_uuid: str, sb_client) -> List[Dict]:
    """
    Fetch all weapons for a user from the user_weapon_inventory table using their user_uuid.
    """
    result = await sb_client.table("user_weapon_inventory").select("*").eq("user_id", user_uuid).execute()
    return result.data or []

# Wrapper for agent: user_uuid is injected by backend, not by agent
async def get_user_weapons_agent(*, sb_client, user_uuid=None, **kwargs):
    if not user_uuid:
        raise Exception("user_uuid must be injected by the backend.")
    return await get_user_weapons_backend(user_uuid, sb_client)

user_weapons_tool = Tool(
    name="get_user_weapons",
    description="Fetches all weapons for the current user. No arguments required.",
    func=get_user_weapons_agent,
    coroutine=get_user_weapons_agent,
)

# --- PvE BiS Weapons Tool ---
async def get_pve_bis_weapons() -> List[Dict]:
    """
    Fetches PvE BiS weapons from the public Google Sheet.
    """
    def _read():
        sheet_id = "1FF5HERxelE0PDiUjfu2eoSPrWNtOmsiHd5KggEXEC8g"
        sheet_gid = 620327328
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}"
        df = pd.read_csv(csv_url)
        df.dropna(how='all', inplace=True)
        return df.to_dict(orient='records')
    return await asyncio.to_thread(_read)

pve_bis_weapons_tool = Tool(
    name="get_pve_bis_weapons",
    description="Fetches PvE BiS weapons from the public Google Sheet.",
    func=get_pve_bis_weapons,
    coroutine=get_pve_bis_weapons,
)

# --- PvE Activity BiS Weapons Tool ---
async def get_pve_activity_bis_weapons() -> List[Dict]:
    """
    Fetches PvE BiS weapons BY ACTIVITY from the public Google Sheet.
    """
    def _read():
        sheet_id = "1FF5HERxelE0PDiUjfu2eoSPrWNtOmsiHd5KggEXEC8g"
        sheet_gid = 82085161
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}"
        df = pd.read_csv(csv_url)
        df.dropna(how='all', inplace=True)
        return df.to_dict(orient='records')
    return await asyncio.to_thread(_read)

pve_activity_bis_weapons_tool = Tool(
    name="get_pve_activity_bis_weapons",
    description="Fetches PvE BiS weapons by activity from the public Google Sheet.",
    func=get_pve_activity_bis_weapons,
    coroutine=get_pve_activity_bis_weapons,
)

# --- Endgame Analysis Tool ---
async def get_endgame_analysis_data(sheet_name: Optional[str] = None) -> Any:
    """
    Fetches data from a specific sheet in the Endgame Analysis spreadsheet using the Google Sheets API and a service account.
    """
    def _read():
        SHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"
        SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service_gs = build("sheets", "v4", credentials=creds)
        meta = service_gs.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets = meta.get("sheets", [])
        active_sheets = [
            (s["properties"]["title"], s["properties"]["sheetId"])
            for s in sheets
            if "old" not in s["properties"]["title"].lower() and "outdated" not in s["properties"]["title"].lower()
        ]
        sheet_name_map = {title: gid for title, gid in active_sheets}
        available_sheet_names = list(sheet_name_map.keys())
        if not sheet_name:
            return f"Please specify which sheet you want data from. Available sheets: {available_sheet_names}"
        matches = difflib.get_close_matches(sheet_name, available_sheet_names, n=1, cutoff=0.6)
        if not matches:
            pattern = re.compile(re.escape(sheet_name), re.IGNORECASE)
            matches = [name for name in available_sheet_names if pattern.search(name)]
        if not matches:
            return f"Error: Unknown sheet name '{sheet_name}'. Available sheets: {available_sheet_names}"
        selected_sheet = matches[0]
        gid = sheet_name_map[selected_sheet]
        csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(csv_url)
        df.dropna(how='all', inplace=True)
        data = df.to_dict(orient='records')
        if len(data) > 200:
            return f"Sheet '{selected_sheet}' contains {len(data)} rows, which is too large to return directly. Please ask a more specific query about this sheet."
        return data
    return await asyncio.to_thread(_read)

endgame_analysis_tool = Tool(
    name="get_endgame_analysis_data",
    description="Fetches data from a specific sheet in the Endgame Analysis spreadsheet using the Google Sheets API and a service account. Pass the sheet name as an argument.",
    func=get_endgame_analysis_data,
    coroutine=get_endgame_analysis_data,
)

# --- Weapon Roll Evaluation Tool ---
from typing import Union

# Example synergy matrix and archetype weights (expand as needed)
PERK_SYNERGY_MATRIX = {
    ("demolitionist", "chill clip"): 10,
    ("auto-loading holster", "explosive payload"): 9,
    ("stats for all", "one for all"): 9,
    ("reconstruction", "recombination"): 10,
}
ARCHETYPE_WEIGHTS = {
    "fusion rifle": {"controlled burst": 2, "kickstart": 2},
    "shotgun": {"opening shot": 2, "surplus": 1},
    "scout rifle": {"explosive payload": 2, "firefly": 1},
}

TIER_THRESHOLDS = [(9, "S"), (7, "A"), (5, "B"), (0, "C")]

async def evaluate_weapon_rolls(
    weapons: Union[dict, list],
    context: str = "pve_group"
) -> Union[dict, list]:
    """
    Evaluates one or more Destiny 2 weapon rolls for a given context (e.g., PvE solo, PvE group, PvP).
    Returns a score, tier, and explanation for each weapon.
    Args:
        weapons: A single weapon dict or a list of weapon dicts. Each dict should have at least:
            - 'archetype' (str)
            - 'column3' (str): Perk in column 3
            - 'column4' (str): Perk in column 4
        context: One of 'pve_solo', 'pve_group', 'pvp'.
    Returns:
        For single weapon: dict with 'score', 'tier', 'explanation'.
        For list: list of such dicts (one per weapon).
    """
    def score_weapon(weapon):
        archetype = weapon.get("archetype", "").lower()
        c3 = weapon.get("column3", "").lower()
        c4 = weapon.get("column4", "").lower()
        perks = (c3, c4)
        # Synergy score
        synergy_score = PERK_SYNERGY_MATRIX.get(perks, 0)
        # Archetype weighting
        arch_weights = ARCHETYPE_WEIGHTS.get(archetype, {})
        arch_score = arch_weights.get(c3, 0) + arch_weights.get(c4, 0)
        # Context bonus (expand as needed)
        context_bonus = 0
        if context == "pve_solo" and c3 in ["wellspring", "heal clip"]:
            context_bonus += 1
        if context == "pvp" and c3 in ["rangefinder", "opening shot"]:
            context_bonus += 1
        # Total score
        total = synergy_score + arch_score + context_bonus
        # Tier
        tier = next(t for thresh, t in TIER_THRESHOLDS if total >= thresh)
        # Explanation
        explanation = f"{c3.title()} + {c4.title()} on a {archetype.title()} scores {total}/10 for {context.replace('_', ' ').upper()}. "
        if synergy_score:
            explanation += f"This combo is highly synergistic. "
        if arch_score:
            explanation += f"Perks match the archetype's strengths. "
        if context_bonus:
            explanation += f"Perks are especially good for {context.replace('_', ' ')}. "
        if not (synergy_score or arch_score or context_bonus):
            explanation += "This roll is functional but not outstanding for this context. "
        return {
            "score": total,
            "tier": tier,
            "explanation": explanation.strip(),
            "weapon": weapon,
        }
    # Handle batch or single
    if isinstance(weapons, list):
        return [score_weapon(w) for w in weapons]
    else:
        return score_weapon(weapons)

evaluate_weapon_rolls_tool = Tool(
    name="evaluate_weapon_rolls",
    description="Evaluates one or more Destiny 2 weapon rolls for a given context (e.g., PvE solo, PvE group, PvP). Returns a score, tier, and explanation for each weapon. Pass a single weapon dict or a list of weapon dicts, plus a context string.",
    func=evaluate_weapon_rolls,
    coroutine=evaluate_weapon_rolls,
)

# Export all tools
WEAPONS_AGENT_TOOLS = [
    user_weapons_tool,
    pve_bis_weapons_tool,
    pve_activity_bis_weapons_tool,
    endgame_analysis_tool,
    evaluate_weapon_rolls_tool,
] 