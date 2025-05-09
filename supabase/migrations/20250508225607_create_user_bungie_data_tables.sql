-- supabase/migrations/YYYYMMDDHHMMSS_create_user_bungie_data_tables.sql

-- Table to store user-specific catalyst status
CREATE TABLE public.user_catalyst_status (
    user_id TEXT NOT NULL,                            -- References user (e.g., Bungie ID)
    catalyst_record_hash BIGINT NOT NULL,             -- DestinyRecordDefinition hash for the catalyst
    is_complete BOOLEAN NOT NULL DEFAULT false,       -- Whether the catalyst objectives are fully complete
    objectives JSONB NULL,                            -- Detailed objective progress { objectiveHash: progress, ... }
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),  -- When this record was last updated from Bungie API

    -- Composite primary key
    PRIMARY KEY (user_id, catalyst_record_hash)
);

-- Optional: Index for faster lookups by user_id
CREATE INDEX idx_user_catalyst_status_user_id ON public.user_catalyst_status(user_id);

-- Add comments to clarify columns
COMMENT ON COLUMN public.user_catalyst_status.user_id IS 'User identifier (e.g., Bungie membership ID).';
COMMENT ON COLUMN public.user_catalyst_status.catalyst_record_hash IS 'Hash identifier linking to DestinyRecordDefinition for the specific catalyst.';
COMMENT ON COLUMN public.user_catalyst_status.is_complete IS 'True if all catalyst objectives are met.';
COMMENT ON COLUMN public.user_catalyst_status.objectives IS 'JSONB storing progress for each objective, keyed by DestinyObjectiveDefinition hash.';
COMMENT ON COLUMN public.user_catalyst_status.last_updated IS 'Timestamp of the last successful synchronization with the Bungie API for this catalyst entry.';

-- Table to store user weapon inventory instances
CREATE TABLE public.user_weapon_inventory (
    user_id TEXT NOT NULL,                           -- References user (e.g., Bungie ID)
    item_instance_id TEXT NOT NULL,                  -- Unique instance ID for this specific weapon copy
    item_hash BIGINT NOT NULL,                       -- DestinyInventoryItemDefinition hash for the base weapon type
    location TEXT NULL,                              -- Where the item is (e.g., 'vault', character ID, 'inventory')
    is_equipped BOOLEAN NOT NULL DEFAULT false,      -- Whether the weapon is currently equipped by a character
    perks JSONB NULL,                                -- Stores equipped perk details (e.g., { perkHash: plugItemHash, ... } or list of plugHashes)
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(), -- When this record was last updated from Bungie API

    -- Composite primary key
    PRIMARY KEY (user_id, item_instance_id)
);

-- Indexes for common lookups
CREATE INDEX idx_user_weapon_inventory_user_id ON public.user_weapon_inventory(user_id);
CREATE INDEX idx_user_weapon_inventory_item_hash ON public.user_weapon_inventory(item_hash);

-- Add comments
COMMENT ON COLUMN public.user_weapon_inventory.user_id IS 'User identifier (e.g., Bungie membership ID).';
COMMENT ON COLUMN public.user_weapon_inventory.item_instance_id IS 'The unique instance ID provided by the Bungie API for this specific weapon copy.';
COMMENT ON COLUMN public.user_weapon_inventory.item_hash IS 'Hash identifier linking to DestinyInventoryItemDefinition for the base weapon type.';
COMMENT ON COLUMN public.user_weapon_inventory.location IS 'Current location of the weapon (e.g., vault, character ID, inventory).';
COMMENT ON COLUMN public.user_weapon_inventory.is_equipped IS 'True if the weapon is currently equipped by a character.';
COMMENT ON COLUMN public.user_weapon_inventory.perks IS 'JSONB storing information about the equipped perks/mods on this weapon instance.';
COMMENT ON COLUMN public.user_weapon_inventory.last_updated IS 'Timestamp of the last successful synchronization with the Bungie API for this weapon entry.';
