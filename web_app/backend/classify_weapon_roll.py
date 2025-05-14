import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Socket Category Hash for main weapon perks (typically columns 3 and 4)
WEAPON_PERKS_SOCKET_CATEGORY_HASH = 4241085061 
# Known PCIs for broad categories - use with 'in' for flexibility
BARREL_PCI_KEYWORD = 'barrel'  # Covers 'barrels', 'weapon.mod.barrel', etc.
MAGAZINE_PCI_KEYWORD = 'magazine' # Covers 'magazines', 'weapon.mod.magazine', etc.
ORIGIN_TRAIT_PCI_KEYWORD = 'origins'
INTRINSIC_PCI_KEYWORD = 'intrinsics'
MASTERWORK_PCI_KEYWORD = 'masterwork' # Covers 'plugs.masterworks.weapons.default', etc.
SHADER_PCI_KEYWORD = 'shader'
MOD_ITEM_CATEGORY_HASH = 610365472 # ItemCategoryHash for "Weapon Mods"


def _extract_perk_details(plug_hash: int, all_plug_definitions: Dict[int, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Helper to get perk details from its definition."""
    plug_def = all_plug_definitions.get(plug_hash)
    if not plug_def:
        # logger.warning(f"Plug definition not found for hash: {plug_hash}")
        return None
    
    display_props = plug_def.get('displayProperties', {})
    perk_name = display_props.get('name')
    
    # Filter out placeholder/empty/undesirable perks early
    # Also filter out intrinsic "Frames" if they are processed as regular perks
    if not perk_name or \
       'empty' in perk_name.lower() or \
       'default' in perk_name.lower() or \
       '(random mod)' in perk_name.lower() or \
       (plug_def.get("itemTypeDisplayName", "").lower() == "intrinsic" and "frame" in perk_name.lower()):
        return None

    perk_description = display_props.get('description', '')
    perk_icon_path = display_props.get('icon', '')
    perk_icon_url = f"https://www.bungie.net{perk_icon_path}" if perk_icon_path else "https://www.bungie.net/common/destiny2_content/icons/broken_icon.png"
    
    return {
        "perk_hash": plug_hash,
        "name": perk_name,
        "description": perk_description,
        "icon_url": perk_icon_url,
        "item_type_display_name": plug_def.get("itemTypeDisplayName", "")
    }

def _extract_plugs_from_socket_entry(
    socket_entry_def: Dict[str, Any],
    all_plug_definitions: Dict[int, Dict[str, Any]],
    plug_set_definitions: Dict[int, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extracts all possible plug details from a socket entry,
    considering its reusablePlugItems and randomizedPlugSetHash.
    """
    possible_perks = []
    
    # Option 1: Direct reusablePlugItems in the socketEntry itself (less common for randomized rolls)
    # Option 2: Plugs from a DestinyPlugSetDefinition (more common for randomized rolls)
    # Order of checking these might matter if a socket somehow has both, but typically one is primary.
    
    # Prioritize plug sets for randomized perks
    plug_set_hash = socket_entry_def.get('randomizedPlugSetHash') or socket_entry_def.get('reusablePlugSetHash')
    if plug_set_hash:
        plug_set_def = plug_set_definitions.get(plug_set_hash)
        if plug_set_def and 'reusablePlugItems' in plug_set_def:
            for plug_item in plug_set_def['reusablePlugItems']:
                # Check 'currentlyCanRoll' if you only want currently available perks
                # For "all possible" including sunsetted/past season, don't filter by currentlyCanRoll
                if plug_item.get('currentlyCanRoll', True): # Default to True if field is missing
                    plug_hash = plug_item.get('plugItemHash')
                    if plug_hash:
                        details = _extract_perk_details(plug_hash, all_plug_definitions)
                        if details:
                            possible_perks.append(details)
        # else:
            # logger.warning(f"Plug set definition not found or malformed for hash: {plug_set_hash}")

    # Fallback or addition: Direct reusablePlugItems in the socketEntry itself
    # This is more for fixed sockets or if plug sets don't cover everything (e.g. intrinsic, masterwork options)
    for plug_item in socket_entry_def.get('reusablePlugItems', []):
        plug_hash = plug_item.get('plugItemHash')
        if plug_hash:
            details = _extract_perk_details(plug_hash, all_plug_definitions)
            if details:
                possible_perks.append(details)
    
    # Deduplicate perks by perk_hash
    unique_perks = []
    seen_hashes = set()
    for perk in possible_perks:
        if perk and perk['perk_hash'] not in seen_hashes:
            unique_perks.append(perk)
            seen_hashes.add(perk['perk_hash'])
            
    return unique_perks


def classify_weapon_roll(
    weapon_definition: Dict[str, Any],
    all_plug_definitions: Dict[int, Dict[str, Any]],
    plug_set_definitions: Dict[int, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Classifies all possible weapon perks for a given weapon definition
    into structured columns (barrels, magazines, traits, origin, etc.).
    """
    weapon_name = weapon_definition.get('displayProperties', {}).get('name', 'Unknown Weapon')
    logger.info(f"Starting roll classification for: {weapon_name}")

    roll_options: Dict[str, List[Dict[str, Any]]] = {
        "intrinsics": [],
        "barrels": [],
        "magazines": [],
        "traits1": [],
        "traits2": [],
        "origin_trait": [],
        "masterworks": [],
        "mods": [],
        "shaders": [],
    }
    
    trait_socket_candidates: List[tuple[int, List[Dict[str, Any]]]] = [] # (socketIndex, perks_list)
    
    # Build a map of socketIndex to its primary socketCategoryHash for quick lookup
    socket_index_to_category_hash_map: Dict[int, int] = {}
    for sc_def in weapon_definition.get("sockets", {}).get("socketCategories", []):
        category_hash = sc_def.get("socketCategoryHash")
        if category_hash:
            for s_idx in sc_def.get("socketIndexes", []):
                # It's possible a socketIndex is in multiple categories,
                # but for WEAPON_PERKS_SOCKET_CATEGORY_HASH it should be fairly exclusive.
                # Prioritize it if so, otherwise take the first one encountered.
                if category_hash == WEAPON_PERKS_SOCKET_CATEGORY_HASH:
                     socket_index_to_category_hash_map[s_idx] = category_hash
                elif s_idx not in socket_index_to_category_hash_map: # If not already mapped by a higher priority category
                    socket_index_to_category_hash_map[s_idx] = category_hash


    socket_entries = weapon_definition.get("sockets", {}).get("socketEntries", [])

    for se_idx, se_def in enumerate(socket_entries): # se_idx is the index in the socketEntries array
        # The crucial socketIndex for ordering within the definition's view of sockets
        socket_index_in_def_view = se_def.get("socketIndex") 
        if socket_index_in_def_view is None:
            # This should ideally not happen if the definition is well-formed.
            # logger.warning(f"Socket entry at array index {se_idx} for {weapon_name} is missing 'socketIndex' field. Skipping.")
            continue

        current_socket_options = _extract_plugs_from_socket_entry(se_def, all_plug_definitions, plug_set_definitions)
        if not current_socket_options: # If no valid perks found for this socket, skip further classification for it
            continue

        # --- Trait Column Identification (D2Checklist Method) ---
        socket_category_hash_for_this_socket = socket_index_to_category_hash_map.get(socket_index_in_def_view)

        if socket_category_hash_for_this_socket == WEAPON_PERKS_SOCKET_CATEGORY_HASH:
            trait_socket_candidates.append( (socket_index_in_def_view, current_socket_options) )
            continue # This socket is handled as a trait, move to next socket_entry

        # --- Other Categories (PCI or ItemCategoryHash based) ---
        # Use initial plug for PCI based classification for non-trait sockets
        initial_plug_hash = se_def.get("singleInitialItemHash")
        pci = ''
        initial_plug_def = None
        if initial_plug_hash and initial_plug_hash != 0:
            initial_plug_def = all_plug_definitions.get(initial_plug_hash)
            if initial_plug_def:
                pci = initial_plug_def.get('plug', {}).get('plugCategoryIdentifier', '').lower()
        
        # Debugging:
        # initial_plug_name = initial_plug_def.get('displayProperties',{}).get('name','N/A') if initial_plug_def else 'N/A'
        # logger.debug(f"Socket Def Idx: {socket_index_in_def_view}, PCI: '{pci}', InitialPlug: '{initial_plug_name}', CategoryHash: {socket_category_hash_for_this_socket}, Options: {len(current_socket_options)}")

        classified_non_trait = False
        if pci: # Only proceed if PCI is available
            if BARREL_PCI_KEYWORD in pci:
                roll_options["barrels"].extend(current_socket_options)
                classified_non_trait = True
            elif MAGAZINE_PCI_KEYWORD in pci:
                roll_options["magazines"].extend(current_socket_options)
                classified_non_trait = True
            elif ORIGIN_TRAIT_PCI_KEYWORD in pci:
                roll_options["origin_trait"].extend(current_socket_options)
                classified_non_trait = True
            elif INTRINSIC_PCI_KEYWORD in pci:
                roll_options["intrinsics"].extend(current_socket_options)
                classified_non_trait = True
            elif MASTERWORK_PCI_KEYWORD in pci:
                 # Filter out "Empty Masterwork Socket" if it's the initial plug, but keep actual MW options
                actual_mw_options = [p for p in current_socket_options if "empty masterwork socket" not in p.get('name','').lower()]
                if actual_mw_options:
                    roll_options["masterworks"].extend(actual_mw_options)
                classified_non_trait = True
            elif SHADER_PCI_KEYWORD in pci:
                # Filter out "Default Shader" or "Empty Shader Socket"
                actual_shader_options = [p for p in current_socket_options if not ("default shader" in p.get('name','').lower() or "empty shader socket" in p.get('name','').lower())]
                if actual_shader_options:
                    roll_options["shaders"].extend(actual_shader_options)
                classified_non_trait = True
        
        # Fallback/additional check for mods using ItemCategoryHash (if not already classified by PCI)
        if not classified_non_trait and initial_plug_def:
            if initial_plug_def.get("itemCategoryHashes") and MOD_ITEM_CATEGORY_HASH in initial_plug_def.get("itemCategoryHashes", []):
                # Filter out "Empty Mod Socket" itself
                actual_mod_options = [p for p in current_socket_options if "empty mod socket" not in p.get('name','').lower()]
                if actual_mod_options: # Only add if there are actual mods, not just the empty placeholder
                    roll_options["mods"].extend(actual_mod_options)


    # Sort trait socket candidates by their original socketIndex and assign
    trait_socket_candidates.sort(key=lambda item: item[0])
    
    if len(trait_socket_candidates) > 0:
        roll_options["traits1"] = trait_socket_candidates[0][1]
    if len(trait_socket_candidates) > 1:
        roll_options["traits2"] = trait_socket_candidates[1][1]
    if len(trait_socket_candidates) > 2:
        logger.warning(f"Weapon {weapon_name} has {len(trait_socket_candidates)} sockets in WEAPON_PERKS_SOCKET_CATEGORY_HASH. Storing first two as traits1/traits2.")
        # Optionally, could put extras into a "traits_extra" list
        # roll_options["traits_extra"] = [tc[1] for tc in trait_socket_candidates[2:]]

    # Final deduplication pass for each category, just in case
    for category_key in roll_options:
        unique_perks_in_category = []
        seen_perk_hashes = set()
        for perk_detail in roll_options[category_key]:
            if perk_detail['perk_hash'] not in seen_perk_hashes:
                unique_perks_in_category.append(perk_detail)
                seen_perk_hashes.add(perk_detail['perk_hash'])
        roll_options[category_key] = unique_perks_in_category
    
    logger.info(f"Finished roll classification for: {weapon_name}. Traits1: {len(roll_options['traits1'])}, Traits2: {len(roll_options['traits2'])}")
    return roll_options

# Example usage (for direct testing, if ever needed):
if __name__ == '__main__':
    # This would require mock data for weapon_definition, all_plug_definitions, plug_set_definitions
    print("classify_weapon_roll.py loaded. Needs to be called with appropriate data.")
    pass 