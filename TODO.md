# Project TODO List

## Phase 1: Finalize Weapon Inventory Sync & Security

- [ ] **1. Verify Remote Table Structure (`user_weapon_inventory`)**
    - Go to Supabase Dashboard > Table Editor > `user_weapon_inventory`.
    - Confirm all columns match the last successful migration (`..._migrate_weapon_inventory_to_detailed_perks.sql`):
        - `col1_plugs`, `col2_plugs`, `col3_trait1`, `col4_trait2`, `origin_trait`, `masterwork`, `weapon_mods`, `shaders` are present and type `text[]`.
        - `intrinsic_perk` is present and type `text`.
        - Old perk columns (e.g., `perks`, `barrel_perks` as JSONB) are gone.
    - Check the RLS policy tab: should show "Allow all for authenticated users" (this is temporary).

- [ ] **2. Test `sync_user_data.py` Script**
    - Run `python scripts/sync_user_data.py`.
    - Monitor logs for errors (API fetch, Supabase upsert).
    - After successful run, inspect the `user_weapon_inventory` table in Supabase Dashboard:
        - Is data being populated correctly?
        - Do the perk arrays (`col1_plugs`, etc.) look like lists of perk names?
        - Does `intrinsic_perk` have the correct frame/intrinsic name?

- [ ] **3. Implement Robust RLS for `user_weapon_inventory` (Security Enhancement)**
    - **3.1. Create `user_profiles` Table (if it doesn't exist or isn't suitable)**
        - Create a new Supabase migration file (e.g., `supabase migration new create_user_profiles_table`).
        - Add the following SQL to the new migration file:
          ```sql
          -- In new migration file (e.g., ..._create_user_profiles_table.sql)
          BEGIN;

          CREATE TABLE IF NOT EXISTS public.user_profiles (
              id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE, -- Links to auth.users.id (Supabase auth user)
              bungie_membership_id TEXT UNIQUE NOT NULL, -- Stores the Bungie Membership ID (from your current user_id column)
              -- Consider adding other profile fields like bungie_display_name, bungie_display_name_code, etc.
              created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
              updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now())
          );

          ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

          DROP POLICY IF EXISTS "Users can manage their own profile" ON public.user_profiles;
          CREATE POLICY "Users can manage their own profile"
          ON public.user_profiles FOR ALL
          USING (auth.uid() = id)
          WITH CHECK (auth.uid() = id);

          COMMENT ON TABLE public.user_profiles IS 'Stores user profile data, linking Supabase auth users to their Bungie membership IDs.';
          COMMENT ON COLUMN public.user_profiles.id IS 'Supabase auth.users.id of the user.';
          COMMENT ON COLUMN public.user_profiles.bungie_membership_id IS 'Unique Bungie membership ID for the user.';

          COMMIT;
          ```
        - Apply the migration: `supabase db push`.

    - **3.2. Populate `user_profiles` Table**
        - Modify your application's authentication flow or a user setup script:
            - When a user logs in via Bungie OAuth and you get their `bungie_membership_id` and their Supabase `auth.uid()` (after they sign up/log in to your Supabase auth).
            - Upsert a record into `public.user_profiles` mapping `auth.uid()` to `bungie_membership_id`.

    - **3.3. Update RLS Policies for `user_weapon_inventory`**
        - Create a new Supabase migration file (e.g., `supabase migration new update_weapon_inventory_rls`).
        - Add the following SQL to this new migration file:
          ```sql
          -- In new migration file (e.g., ..._update_weapon_inventory_rls.sql)
          BEGIN;

          -- Drop the temporary permissive policy
          DROP POLICY IF EXISTS "Allow all for authenticated users" ON public.user_weapon_inventory;

          -- New RLS Policies for user_weapon_inventory
          DROP POLICY IF EXISTS "Users can read their own weapon inventory" ON public.user_weapon_inventory;
          CREATE POLICY "Users can read their own weapon inventory"
          ON public.user_weapon_inventory FOR SELECT TO authenticated
          USING (
              EXISTS (
                  SELECT 1 FROM public.user_profiles prof
                  WHERE prof.id = auth.uid() AND prof.bungie_membership_id = user_id -- user_id here is from user_weapon_inventory
              )
          );

          DROP POLICY IF EXISTS "Users can insert their own weapon inventory" ON public.user_weapon_inventory;
          CREATE POLICY "Users can insert their own weapon inventory"
          ON public.user_weapon_inventory FOR INSERT TO authenticated
          WITH CHECK (
              EXISTS (
                  SELECT 1 FROM public.user_profiles prof
                  WHERE prof.id = auth.uid() AND prof.bungie_membership_id = user_id
              )
          );

          DROP POLICY IF EXISTS "Users can update their own weapon inventory" ON public.user_weapon_inventory;
          CREATE POLICY "Users can update their own weapon inventory"
          ON public.user_weapon_inventory FOR UPDATE TO authenticated
          USING (
              EXISTS (
                  SELECT 1 FROM public.user_profiles prof
                  WHERE prof.id = auth.uid() AND prof.bungie_membership_id = user_id
              )
          )
          WITH CHECK (
              EXISTS (
                  SELECT 1 FROM public.user_profiles prof
                  WHERE prof.id = auth.uid() AND prof.bungie_membership_id = user_id
              )
          );

          DROP POLICY IF EXISTS "Users can delete their own weapon inventory" ON public.user_weapon_inventory;
          CREATE POLICY "Users can delete their own weapon inventory"
          ON public.user_weapon_inventory FOR DELETE TO authenticated
          USING (
              EXISTS (
                  SELECT 1 FROM public.user_profiles prof
                  WHERE prof.id = auth.uid() AND prof.bungie_membership_id = user_id
              )
          );

          COMMIT;
          ```
        - Apply the migration: `supabase db push`.

- [ ] **4. Optional: Refactor `user_id` in `user_weapon_inventory` (Advanced)**
    - Consider if `user_weapon_inventory.user_id` should directly store `auth.users.id` (UUID) instead of Bungie ID.
    - This would simplify RLS policies but would require `sync_user_data.py` to know the `auth.uid()` for the Bungie user it's syncing.
    - This might involve looking up the `auth.uid()` from `user_profiles` using the Bungie ID during the sync, or having the sync script run in a context where `auth.uid()` is available.
    - *Decision: Defer this unless current RLS with `user_profiles` link becomes problematic or inefficient.*

## Phase 2: Further Enhancements (Future)

- [ ] Review and refine error handling in `sync_user_data.py`, especially for Supabase client responses.
- [ ] Update `scripts/test_weapon_roll_extraction.py` to also extract `intrinsic_perk` if it's to be used as a standalone test/debug script for the full weapon structure.
- [ ] Consider database indexing strategies for `user_weapon_inventory` based on common query patterns (e.g., on `item_hash`, specific perk columns if frequently filtered). 