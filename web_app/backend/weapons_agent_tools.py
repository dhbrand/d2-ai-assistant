from langchain.tools import Tool, StructuredTool
from typing import List, Dict, Optional, Any, Union
import pandas as pd
import difflib
import re
import os
import asyncio
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel, ValidationError, Field

# Table schema for user_weapon_inventory (for tool description)
USER_WEAPON_INVENTORY_SCHEMA = [
    "item_instance_id", "item_hash", "weapon_name", "weapon_type", "intrinsic_perk",
    "col1_plugs", "col2_plugs", "col3_trait1", "col4_trait2", "origin_trait",
    "masterwork", "weapon_mods", "shaders", "location", "is_equipped", "last_updated", "is_adept", "user_id"
]

# Async tool to fetch all weapons for a user from Supabase, with flexible query support
async def get_user_weapons_backend(user_uuid: str, sb_client, filters: dict = None, fuzzy_filters: dict = None, aggregate: str = None, group_by: str = None) -> Any:
    """
    Fetches weapons for a user from the user_weapon_inventory table, with optional filtering, fuzzy filtering, aggregation, and grouping.
    Args:
        user_uuid: The user's UUID (injected by backend).
        filters: Optional dict of column-value pairs for exact match (e.g., {"weapon_type": "Pulse Rifle"}).
        fuzzy_filters: Optional dict of column-value pairs for partial/case-insensitive match (e.g., {"weapon_name": "rifle"}).
        aggregate: Optional aggregate function ("count").
        group_by: Optional column to group by (e.g., "weapon_type").
    Returns:
        - If aggregate is set, returns the aggregate result (e.g., count).
        - If filters/group_by are set, returns filtered/grouped results.
        - Otherwise, returns the full weapon list.
    """
    # For count, use count="exact" and do NOT fetch all rows
    if aggregate == "count":
        query = sb_client.table("user_weapon_inventory").select("*", count="exact").eq("user_id", user_uuid)
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        if fuzzy_filters:
            for col, val in fuzzy_filters.items():
                query = query.ilike(col, f"%{val}%")
        result = await query.execute()
        count = result.count if hasattr(result, "count") and result.count is not None else (len(result.data) if result.data else 0)
        if group_by:
            from collections import Counter
            group_counts = Counter(item.get(group_by) for item in (result.data or []))
            return dict(group_counts)
        return {"count": count}
    # For all other queries, always fetch up to 10,000 rows (disables pagination for most use cases)
    query = sb_client.table("user_weapon_inventory").select("*").eq("user_id", user_uuid).range(0, 9999)
    if filters:
        for col, val in filters.items():
            query = query.eq(col, val)
    if fuzzy_filters:
        for col, val in fuzzy_filters.items():
            query = query.ilike(col, f"%{val}%")
    if group_by:
        result = await query.execute()
        from collections import defaultdict
        grouped = defaultdict(list)
        for item in (result.data or []):
            if "Error: An unexpected error occurred: 'weapon_type'" not in str(item):
                item["weapon_type"] = "Unknown"
            grouped[item.get(group_by)].append(item)
        return dict(grouped)
    result = await query.execute()
    weapons = result.data or []
    for w in weapons:
        if "weapon_type" not in w:
            w["weapon_type"] = "Unknown"
    return weapons

# Wrapper for agent: user_uuid is injected by backend, not by agent
async def get_user_weapons_agent(*, sb_client, user_uuid=None, filters=None, fuzzy_filters=None, aggregate=None, group_by=None, **kwargs):
    if not user_uuid:
        raise Exception("user_uuid must be injected by the backend.")
    return await get_user_weapons_backend(user_uuid, sb_client, filters=filters, fuzzy_filters=fuzzy_filters, aggregate=aggregate, group_by=group_by)

user_weapons_tool = Tool(
    name="get_user_weapons",
    description=(
        "Fetches weapons for the current user from the user_weapon_inventory table. "
        "Supports optional exact filtering (filters), fuzzy filtering (fuzzy_filters), aggregation, and grouping.\n"
        "Available columns for filtering/grouping: " + ", ".join(USER_WEAPON_INVENTORY_SCHEMA) + ".\n"
        "Parameters:\n"
        "- filters: dict of column-value pairs for exact match (e.g., {'weapon_type': 'Pulse Rifle'}).\n"
        "- fuzzy_filters: dict of column-value pairs for partial/case-insensitive match (e.g., {'weapon_name': 'rifle'}).\n"
        "- aggregate: 'count' to get the number of matching weapons.\n"
        "- group_by: column name to group results (e.g., 'weapon_type').\n"
        "Examples:\n"
        "- get_user_weapons(aggregate='count')  # Count all weapons\n"
        "- get_user_weapons(filters={'weapon_type': 'Pulse Rifle'}, aggregate='count')  # Count pulse rifles (exact match)\n"
        "- get_user_weapons(fuzzy_filters={'weapon_name': 'rifle'})  # List weapons with 'rifle' in the name (fuzzy match)\n"
        "- get_user_weapons(group_by='weapon_type', aggregate='count')  # Count by weapon type\n"
        "Returns either a list of weapons, a count, or a grouped summary."
    ),
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
        data = df.to_dict(orient='records')
        for w in data:
            if "weapon_type" not in w:
                w["weapon_type"] = "Unknown"
        return data
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
        data = df.to_dict(orient='records')
        for w in data:
            if "weapon_type" not in w:
                w["weapon_type"] = "Unknown"
        return data
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
        for w in data:
            if "weapon_type" not in w:
                w["weapon_type"] = "Unknown"
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

class WeaponRoll(BaseModel):
    archetype: str
    column3: str
    column4: str
    # Add more fields as needed

class WeaponRollList(BaseModel):
    weapons: List[WeaponRoll] = Field(..., description="List of weapon rolls to evaluate.")
    context: str = Field("pve_group", description="Context for evaluation: 'pve_solo', 'pve_group', or 'pvp'.")

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
    weapons: Union[List[WeaponRoll], WeaponRoll],
    context: str = "pve_group"
) -> Union[dict, list]:
    """
    Evaluates one or more Destiny 2 weapon rolls for a given context (e.g., PvE solo, PvE group, PvP).
    Returns a score, tier, and explanation for each weapon.
    Input must be a WeaponRoll or list of WeaponRolls, plus context.
    """
    def score_weapon(weapon: WeaponRoll):
        archetype = weapon.archetype.lower()
        c3 = weapon.column3.lower()
        c4 = weapon.column4.lower()
        perks = (c3, c4)
        synergy_score = PERK_SYNERGY_MATRIX.get(perks, 0)
        arch_weights = ARCHETYPE_WEIGHTS.get(archetype, {})
        arch_score = arch_weights.get(c3, 0) + arch_weights.get(c4, 0)
        context_bonus = 0
        if context == "pve_solo" and c3 in ["wellspring", "heal clip"]:
            context_bonus += 1
        if context == "pvp" and c3 in ["rangefinder", "opening shot"]:
            context_bonus += 1
        total = synergy_score + arch_score + context_bonus
        tier = next(t for thresh, t in TIER_THRESHOLDS if total >= thresh)
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
            "weapon": weapon.dict(),
        }
    # Accept both single and batch
    if isinstance(weapons, list):
        return [score_weapon(w) for w in weapons]
    elif isinstance(weapons, WeaponRoll):
        return score_weapon(weapons)
    else:
        return {"error": f"Input must be a WeaponRoll or list of WeaponRolls. Got: {type(weapons).__name__}"}

evaluate_weapon_rolls_tool = StructuredTool.from_function(
    func=lambda weapons, context="pve_group": evaluate_weapon_rolls(weapons=weapons, context=context),
    name="evaluate_weapon_rolls",
    description=(
        "Evaluates one or more Destiny 2 weapon rolls for a given context (PvE solo, PvE group, PvP). "
        "Input must be a WeaponRoll or a list of WeaponRolls, plus context. "
        "Example (single): {'weapons': [{'archetype': 'fusion rifle', 'column3': 'demolitionist', 'column4': 'chill clip'}], 'context': 'pve_group'}. "
        "Returns a score, tier, and explanation for each weapon."
    ),
    args_schema=WeaponRollList,
)

# Export all tools
WEAPONS_AGENT_TOOLS = [
    user_weapons_tool,
    pve_bis_weapons_tool,
    pve_activity_bis_weapons_tool,
    endgame_analysis_tool,
    evaluate_weapon_rolls_tool,
] 