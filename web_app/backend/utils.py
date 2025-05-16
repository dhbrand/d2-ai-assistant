def normalize_catalyst_data(raw: dict) -> dict:
    """
    Normalize catalyst data to ensure all required fields are present for CatalystData Pydantic model.
    Fills in defaults for missing fields and adapts legacy/partial data.
    """
    normalized = {
        "item_hash": raw.get("item_hash") or 0,
        "icon_url": raw.get("icon_url") or "",
        "is_complete": raw.get("is_complete", False),
        "name": raw.get("name", ""),
        "description": raw.get("description", ""),
        "objectives": [],
    }
    objectives = raw.get("objectives", [])
    for obj in objectives:
        normalized_obj = {
            "objective_hash": obj.get("objective_hash") or 0,
            "name": obj.get("name", ""),
            "completion_value": obj.get("completion_value", 0),
            "is_complete": obj.get("is_complete", False),
            "description": obj.get("description", ""),
            "progress": obj.get("progress", 0),
        }
        normalized["objectives"].append(normalized_obj)
    return normalized 