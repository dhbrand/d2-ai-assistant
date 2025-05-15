---
description: 
globs: weapon_api.py
alwaysApply: false
---

# Refer to project goals
From Bungie’s instance data (plugHash values in sockets) and your Supabase manifest, build a structured output like:
```json
{
  "weapon_hash": 3959549446,  
  "weapon_name": "Yarovit MG4",
  "weapon_type": "Submachine Gun",
  "intrinsic_perk": "Lightweight Frame",
  "col1_plugs": [
    "Chambered Compensator",
    "Fluted Barrel"
  ],
  "col2_plugs": [
    "Alloy Magazine",
    "Armor-Piercing Rounds"
  ],
  "col3_trait1": [
    "Rewind Rounds"
  ],
  "col4_trait2": [
    "Headstone"
  ],
  "origin_trait": [],
  "masterwork": [
    "Tier 4: Range"
  ],
  "weapon_mods": [
    "Anti-Flinch",
    "Ballistics",
    "CQC Optics: High",
    "CQC Optics: Low",
    "Heavy Ammo Finder Enhancement",
    "Special Ammo Finder Enhancement",
    "Stunloader",
    "Synergy",
    "Tactical"
  ],
  "shaders": [
    "Default Shader"
  ]
}
```
