    -- In supabase/migrations/20250513185109_migrate_weapon_inventory_to_detailed_perks.sql

    BEGIN; -- Start transaction

    -- Drop old perk columns that might have incorrect types (JSONB) or old names
    ALTER TABLE public.user_weapon_inventory
        DROP COLUMN IF EXISTS perks CASCADE, -- The very old generic JSONB column
        DROP COLUMN IF EXISTS barrel_perks CASCADE, -- Old name, potentially JSONB
        DROP COLUMN IF EXISTS magazine_perks CASCADE, -- Old name, potentially JSONB
        DROP COLUMN IF EXISTS trait_perk_col1 CASCADE, -- Old name, potentially JSONB
        DROP COLUMN IF EXISTS trait_perk_col2 CASCADE, -- Old name, potentially JSONB
        DROP COLUMN IF EXISTS origin_trait CASCADE; -- Dropping to ensure it's recreated as TEXT[]

    -- Create the user_weapon_inventory table if it doesn't exist
    CREATE TABLE IF NOT EXISTS public.user_weapon_inventory (
        user_id TEXT NOT NULL, -- Stores Bungie Membership ID
        item_instance_id TEXT NOT NULL,
        item_hash BIGINT NOT NULL,
        weapon_name TEXT,
        weapon_type TEXT,
        intrinsic_perk TEXT,
        location TEXT,
        is_equipped BOOLEAN DEFAULT false,
        col1_plugs TEXT[],
        col2_plugs TEXT[],
        col3_trait1 TEXT[],
        col4_trait2 TEXT[],
        origin_trait TEXT[], -- Will be recreated as TEXT[]
        masterwork TEXT[],
        weapon_mods TEXT[],
        shaders TEXT[],
        last_updated TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
        PRIMARY KEY (user_id, item_instance_id) -- Composite PK
    );

    -- Add columns if they were dropped or table was just created
    ALTER TABLE public.user_weapon_inventory
        ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL,
        ADD COLUMN IF NOT EXISTS item_hash BIGINT NOT NULL,
        ADD COLUMN IF NOT EXISTS weapon_name TEXT,
        ADD COLUMN IF NOT EXISTS weapon_type TEXT,
        ADD COLUMN IF NOT EXISTS intrinsic_perk TEXT,
        ADD COLUMN IF NOT EXISTS location TEXT,
        ADD COLUMN IF NOT EXISTS is_equipped BOOLEAN DEFAULT false,
        ADD COLUMN IF NOT EXISTS col1_plugs TEXT[],
        ADD COLUMN IF NOT EXISTS col2_plugs TEXT[],
        ADD COLUMN IF NOT EXISTS col3_trait1 TEXT[],
        ADD COLUMN IF NOT EXISTS col4_trait2 TEXT[],
        ADD COLUMN IF NOT EXISTS origin_trait TEXT[],
        ADD COLUMN IF NOT EXISTS masterwork TEXT[],
        ADD COLUMN IF NOT EXISTS weapon_mods TEXT[],
        ADD COLUMN IF NOT EXISTS shaders TEXT[],
        ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL;

    -- Enable Row Level Security
    ALTER TABLE public.user_weapon_inventory ENABLE ROW LEVEL SECURITY;

    -- Basic RLS Policies (These DO NOT link to auth.uid() yet - placeholder for now)
    -- You will need a robust RLS strategy later.
    DROP POLICY IF EXISTS "Allow all for authenticated users" ON public.user_weapon_inventory;
    CREATE POLICY "Allow all for authenticated users"
    ON public.user_weapon_inventory FOR ALL TO authenticated USING (true) WITH CHECK (true);

    -- Comments
    COMMENT ON TABLE public.user_weapon_inventory IS 'Stores detailed information about each user''s weapon instances, including their specific perks. user_id stores Bungie Membership ID.';
    COMMENT ON COLUMN public.user_weapon_inventory.user_id IS 'Bungie Membership ID.';
    COMMENT ON COLUMN public.user_weapon_inventory.intrinsic_perk IS 'The name of the weapon''s intrinsic frame or perk.';

    COMMIT; -- End transaction