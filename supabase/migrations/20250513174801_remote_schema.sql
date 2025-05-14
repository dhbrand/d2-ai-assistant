create table "public"."destinyactivitydefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyactivitymodedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyactivitytypedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyclassdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinycollectibledefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinydamagetypedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinydestinationdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyfactiondefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinygenderdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyinventorybucketdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyinventoryitemdefinition" (
    "hash" bigint not null,
    "json_data" jsonb not null
);


create table "public"."destinymetricdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyobjectivedefinition" (
    "hash" bigint not null,
    "json_data" jsonb not null
);


create table "public"."destinyplacedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyplugsetdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinypresentationnodedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyprogressiondefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyracedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyrecorddefinition" (
    "hash" bigint not null,
    "json_data" jsonb not null
);


create table "public"."destinysandboxperkdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyseasondefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinysocketcategorydefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinysockettypedefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinystatdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinytraitdefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


create table "public"."destinyvendordefinition" (
    "hash" bigint not null,
    "json_data" jsonb
);


-- In your newest migration file (e.g., YYYYMMDDHHMMSS_setup_weapon_inventory_v2.sql)

-- Attempt to drop old columns if they exist and might have wrong types
ALTER TABLE public.user_weapon_inventory
    DROP COLUMN IF EXISTS barrel_perks,
    DROP COLUMN IF EXISTS magazine_perks,
    DROP COLUMN IF EXISTS trait_perk_col1, -- old name
    DROP COLUMN IF EXISTS trait_perk_col2, -- old name
    DROP COLUMN IF EXISTS perks; -- if this old general column exists

-- Then, ensure the table and all correct columns exist
CREATE TABLE IF NOT EXISTS public.user_weapon_inventory (
    user_id TEXT NOT NULL,
    item_instance_id TEXT PRIMARY KEY,
    item_hash BIGINT NOT NULL,
    weapon_name TEXT,
    weapon_type TEXT,
    intrinsic_perk TEXT,
    location TEXT,
    is_equipped BOOLEAN,
    col1_plugs TEXT[],      -- NEW NAME & TYPE
    col2_plugs TEXT[],      -- NEW NAME & TYPE
    col3_trait1 TEXT[],     -- NEW NAME & TYPE
    col4_trait2 TEXT[],     -- NEW NAME & TYPE
    origin_trait TEXT[],    -- ENSURE TYPE IS TEXT[]
    masterwork TEXT[],
    weapon_mods TEXT[],
    shaders TEXT[],
    last_updated TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT user_weapon_inventory_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE
);

-- Add or ensure correct columns (this will add them if CREATE TABLE was skipped or if they were dropped)
ALTER TABLE public.user_weapon_inventory
    ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL,
    -- ... (add all other columns as per the full DDL I provided previously) ...
    ADD COLUMN IF NOT EXISTS intrinsic_perk TEXT,
    ADD COLUMN IF NOT EXISTS col1_plugs TEXT[],
    ADD COLUMN IF NOT EXISTS col2_plugs TEXT[],
    ADD COLUMN IF NOT EXISTS col3_trait1 TEXT[],
    ADD COLUMN IF NOT EXISTS col4_trait2 TEXT[],
    ADD COLUMN IF NOT EXISTS origin_trait TEXT[], -- Ensure it's added as TEXT[] if it was dropped
    ADD COLUMN IF NOT EXISTS masterwork TEXT[],
    ADD COLUMN IF NOT EXISTS weapon_mods TEXT[],
    ADD COLUMN IF NOT EXISTS shaders TEXT[],
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL;

-- ... (Rest of the RLS policies and comments) ...

CREATE UNIQUE INDEX destinyactivitydefinition_pkey ON public.destinyactivitydefinition USING btree (hash);

CREATE UNIQUE INDEX destinyactivitymodedefinition_pkey ON public.destinyactivitymodedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyactivitytypedefinition_pkey ON public.destinyactivitytypedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyclassdefinition_pkey ON public.destinyclassdefinition USING btree (hash);

CREATE UNIQUE INDEX destinycollectibledefinition_pkey ON public.destinycollectibledefinition USING btree (hash);

CREATE UNIQUE INDEX destinydamagetypedefinition_pkey ON public.destinydamagetypedefinition USING btree (hash);

CREATE UNIQUE INDEX destinydestinationdefinition_pkey ON public.destinydestinationdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyfactiondefinition_pkey ON public.destinyfactiondefinition USING btree (hash);

CREATE UNIQUE INDEX destinygenderdefinition_pkey ON public.destinygenderdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyinventorybucketdefinition_pkey ON public.destinyinventorybucketdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyinventoryitemdefinition_pkey ON public.destinyinventoryitemdefinition USING btree (hash);

CREATE UNIQUE INDEX destinymetricdefinition_pkey ON public.destinymetricdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyobjectivedefinition_pkey ON public.destinyobjectivedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyplacedefinition_pkey ON public.destinyplacedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyplugsetdefinition_pkey ON public.destinyplugsetdefinition USING btree (hash);

CREATE UNIQUE INDEX destinypresentationnodedefinition_pkey ON public.destinypresentationnodedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyprogressiondefinition_pkey ON public.destinyprogressiondefinition USING btree (hash);

CREATE UNIQUE INDEX destinyracedefinition_pkey ON public.destinyracedefinition USING btree (hash);

CREATE UNIQUE INDEX destinyrecorddefinition_pkey ON public.destinyrecorddefinition USING btree (hash);

CREATE UNIQUE INDEX destinysandboxperkdefinition_pkey ON public.destinysandboxperkdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyseasondefinition_pkey ON public.destinyseasondefinition USING btree (hash);

CREATE UNIQUE INDEX destinysocketcategorydefinition_pkey ON public.destinysocketcategorydefinition USING btree (hash);

CREATE UNIQUE INDEX destinysockettypedefinition_pkey ON public.destinysockettypedefinition USING btree (hash);

CREATE UNIQUE INDEX destinystatdefinition_pkey ON public.destinystatdefinition USING btree (hash);

CREATE UNIQUE INDEX destinytraitdefinition_pkey ON public.destinytraitdefinition USING btree (hash);

CREATE UNIQUE INDEX destinyvendordefinition_pkey ON public.destinyvendordefinition USING btree (hash);

alter table "public"."destinyactivitydefinition" add constraint "destinyactivitydefinition_pkey" PRIMARY KEY using index "destinyactivitydefinition_pkey";

alter table "public"."destinyactivitymodedefinition" add constraint "destinyactivitymodedefinition_pkey" PRIMARY KEY using index "destinyactivitymodedefinition_pkey";

alter table "public"."destinyactivitytypedefinition" add constraint "destinyactivitytypedefinition_pkey" PRIMARY KEY using index "destinyactivitytypedefinition_pkey";

alter table "public"."destinyclassdefinition" add constraint "destinyclassdefinition_pkey" PRIMARY KEY using index "destinyclassdefinition_pkey";

alter table "public"."destinycollectibledefinition" add constraint "destinycollectibledefinition_pkey" PRIMARY KEY using index "destinycollectibledefinition_pkey";

alter table "public"."destinydamagetypedefinition" add constraint "destinydamagetypedefinition_pkey" PRIMARY KEY using index "destinydamagetypedefinition_pkey";

alter table "public"."destinydestinationdefinition" add constraint "destinydestinationdefinition_pkey" PRIMARY KEY using index "destinydestinationdefinition_pkey";

alter table "public"."destinyfactiondefinition" add constraint "destinyfactiondefinition_pkey" PRIMARY KEY using index "destinyfactiondefinition_pkey";

alter table "public"."destinygenderdefinition" add constraint "destinygenderdefinition_pkey" PRIMARY KEY using index "destinygenderdefinition_pkey";

alter table "public"."destinyinventorybucketdefinition" add constraint "destinyinventorybucketdefinition_pkey" PRIMARY KEY using index "destinyinventorybucketdefinition_pkey";

alter table "public"."destinyinventoryitemdefinition" add constraint "destinyinventoryitemdefinition_pkey" PRIMARY KEY using index "destinyinventoryitemdefinition_pkey";

alter table "public"."destinymetricdefinition" add constraint "destinymetricdefinition_pkey" PRIMARY KEY using index "destinymetricdefinition_pkey";

alter table "public"."destinyobjectivedefinition" add constraint "destinyobjectivedefinition_pkey" PRIMARY KEY using index "destinyobjectivedefinition_pkey";

alter table "public"."destinyplacedefinition" add constraint "destinyplacedefinition_pkey" PRIMARY KEY using index "destinyplacedefinition_pkey";

alter table "public"."destinyplugsetdefinition" add constraint "destinyplugsetdefinition_pkey" PRIMARY KEY using index "destinyplugsetdefinition_pkey";

alter table "public"."destinypresentationnodedefinition" add constraint "destinypresentationnodedefinition_pkey" PRIMARY KEY using index "destinypresentationnodedefinition_pkey";

alter table "public"."destinyprogressiondefinition" add constraint "destinyprogressiondefinition_pkey" PRIMARY KEY using index "destinyprogressiondefinition_pkey";

alter table "public"."destinyracedefinition" add constraint "destinyracedefinition_pkey" PRIMARY KEY using index "destinyracedefinition_pkey";

alter table "public"."destinyrecorddefinition" add constraint "destinyrecorddefinition_pkey" PRIMARY KEY using index "destinyrecorddefinition_pkey";

alter table "public"."destinysandboxperkdefinition" add constraint "destinysandboxperkdefinition_pkey" PRIMARY KEY using index "destinysandboxperkdefinition_pkey";

alter table "public"."destinyseasondefinition" add constraint "destinyseasondefinition_pkey" PRIMARY KEY using index "destinyseasondefinition_pkey";

alter table "public"."destinysocketcategorydefinition" add constraint "destinysocketcategorydefinition_pkey" PRIMARY KEY using index "destinysocketcategorydefinition_pkey";

alter table "public"."destinysockettypedefinition" add constraint "destinysockettypedefinition_pkey" PRIMARY KEY using index "destinysockettypedefinition_pkey";

alter table "public"."destinystatdefinition" add constraint "destinystatdefinition_pkey" PRIMARY KEY using index "destinystatdefinition_pkey";

alter table "public"."destinytraitdefinition" add constraint "destinytraitdefinition_pkey" PRIMARY KEY using index "destinytraitdefinition_pkey";

alter table "public"."destinyvendordefinition" add constraint "destinyvendordefinition_pkey" PRIMARY KEY using index "destinyvendordefinition_pkey";

set check_function_bodies = off;

CREATE OR REPLACE FUNCTION public.execute_dynamic_sql(sql text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
begin
    execute sql;
end;
$function$
;

grant delete on table "public"."destinyactivitydefinition" to "anon";

grant insert on table "public"."destinyactivitydefinition" to "anon";

grant references on table "public"."destinyactivitydefinition" to "anon";

grant select on table "public"."destinyactivitydefinition" to "anon";

grant trigger on table "public"."destinyactivitydefinition" to "anon";

grant truncate on table "public"."destinyactivitydefinition" to "anon";

grant update on table "public"."destinyactivitydefinition" to "anon";

grant delete on table "public"."destinyactivitydefinition" to "authenticated";

grant insert on table "public"."destinyactivitydefinition" to "authenticated";

grant references on table "public"."destinyactivitydefinition" to "authenticated";

grant select on table "public"."destinyactivitydefinition" to "authenticated";

grant trigger on table "public"."destinyactivitydefinition" to "authenticated";

grant truncate on table "public"."destinyactivitydefinition" to "authenticated";

grant update on table "public"."destinyactivitydefinition" to "authenticated";

grant delete on table "public"."destinyactivitydefinition" to "service_role";

grant insert on table "public"."destinyactivitydefinition" to "service_role";

grant references on table "public"."destinyactivitydefinition" to "service_role";

grant select on table "public"."destinyactivitydefinition" to "service_role";

grant trigger on table "public"."destinyactivitydefinition" to "service_role";

grant truncate on table "public"."destinyactivitydefinition" to "service_role";

grant update on table "public"."destinyactivitydefinition" to "service_role";

grant delete on table "public"."destinyactivitymodedefinition" to "anon";

grant insert on table "public"."destinyactivitymodedefinition" to "anon";

grant references on table "public"."destinyactivitymodedefinition" to "anon";

grant select on table "public"."destinyactivitymodedefinition" to "anon";

grant trigger on table "public"."destinyactivitymodedefinition" to "anon";

grant truncate on table "public"."destinyactivitymodedefinition" to "anon";

grant update on table "public"."destinyactivitymodedefinition" to "anon";

grant delete on table "public"."destinyactivitymodedefinition" to "authenticated";

grant insert on table "public"."destinyactivitymodedefinition" to "authenticated";

grant references on table "public"."destinyactivitymodedefinition" to "authenticated";

grant select on table "public"."destinyactivitymodedefinition" to "authenticated";

grant trigger on table "public"."destinyactivitymodedefinition" to "authenticated";

grant truncate on table "public"."destinyactivitymodedefinition" to "authenticated";

grant update on table "public"."destinyactivitymodedefinition" to "authenticated";

grant delete on table "public"."destinyactivitymodedefinition" to "service_role";

grant insert on table "public"."destinyactivitymodedefinition" to "service_role";

grant references on table "public"."destinyactivitymodedefinition" to "service_role";

grant select on table "public"."destinyactivitymodedefinition" to "service_role";

grant trigger on table "public"."destinyactivitymodedefinition" to "service_role";

grant truncate on table "public"."destinyactivitymodedefinition" to "service_role";

grant update on table "public"."destinyactivitymodedefinition" to "service_role";

grant delete on table "public"."destinyactivitytypedefinition" to "anon";

grant insert on table "public"."destinyactivitytypedefinition" to "anon";

grant references on table "public"."destinyactivitytypedefinition" to "anon";

grant select on table "public"."destinyactivitytypedefinition" to "anon";

grant trigger on table "public"."destinyactivitytypedefinition" to "anon";

grant truncate on table "public"."destinyactivitytypedefinition" to "anon";

grant update on table "public"."destinyactivitytypedefinition" to "anon";

grant delete on table "public"."destinyactivitytypedefinition" to "authenticated";

grant insert on table "public"."destinyactivitytypedefinition" to "authenticated";

grant references on table "public"."destinyactivitytypedefinition" to "authenticated";

grant select on table "public"."destinyactivitytypedefinition" to "authenticated";

grant trigger on table "public"."destinyactivitytypedefinition" to "authenticated";

grant truncate on table "public"."destinyactivitytypedefinition" to "authenticated";

grant update on table "public"."destinyactivitytypedefinition" to "authenticated";

grant delete on table "public"."destinyactivitytypedefinition" to "service_role";

grant insert on table "public"."destinyactivitytypedefinition" to "service_role";

grant references on table "public"."destinyactivitytypedefinition" to "service_role";

grant select on table "public"."destinyactivitytypedefinition" to "service_role";

grant trigger on table "public"."destinyactivitytypedefinition" to "service_role";

grant truncate on table "public"."destinyactivitytypedefinition" to "service_role";

grant update on table "public"."destinyactivitytypedefinition" to "service_role";

grant delete on table "public"."destinyclassdefinition" to "anon";

grant insert on table "public"."destinyclassdefinition" to "anon";

grant references on table "public"."destinyclassdefinition" to "anon";

grant select on table "public"."destinyclassdefinition" to "anon";

grant trigger on table "public"."destinyclassdefinition" to "anon";

grant truncate on table "public"."destinyclassdefinition" to "anon";

grant update on table "public"."destinyclassdefinition" to "anon";

grant delete on table "public"."destinyclassdefinition" to "authenticated";

grant insert on table "public"."destinyclassdefinition" to "authenticated";

grant references on table "public"."destinyclassdefinition" to "authenticated";

grant select on table "public"."destinyclassdefinition" to "authenticated";

grant trigger on table "public"."destinyclassdefinition" to "authenticated";

grant truncate on table "public"."destinyclassdefinition" to "authenticated";

grant update on table "public"."destinyclassdefinition" to "authenticated";

grant delete on table "public"."destinyclassdefinition" to "service_role";

grant insert on table "public"."destinyclassdefinition" to "service_role";

grant references on table "public"."destinyclassdefinition" to "service_role";

grant select on table "public"."destinyclassdefinition" to "service_role";

grant trigger on table "public"."destinyclassdefinition" to "service_role";

grant truncate on table "public"."destinyclassdefinition" to "service_role";

grant update on table "public"."destinyclassdefinition" to "service_role";

grant delete on table "public"."destinycollectibledefinition" to "anon";

grant insert on table "public"."destinycollectibledefinition" to "anon";

grant references on table "public"."destinycollectibledefinition" to "anon";

grant select on table "public"."destinycollectibledefinition" to "anon";

grant trigger on table "public"."destinycollectibledefinition" to "anon";

grant truncate on table "public"."destinycollectibledefinition" to "anon";

grant update on table "public"."destinycollectibledefinition" to "anon";

grant delete on table "public"."destinycollectibledefinition" to "authenticated";

grant insert on table "public"."destinycollectibledefinition" to "authenticated";

grant references on table "public"."destinycollectibledefinition" to "authenticated";

grant select on table "public"."destinycollectibledefinition" to "authenticated";

grant trigger on table "public"."destinycollectibledefinition" to "authenticated";

grant truncate on table "public"."destinycollectibledefinition" to "authenticated";

grant update on table "public"."destinycollectibledefinition" to "authenticated";

grant delete on table "public"."destinycollectibledefinition" to "service_role";

grant insert on table "public"."destinycollectibledefinition" to "service_role";

grant references on table "public"."destinycollectibledefinition" to "service_role";

grant select on table "public"."destinycollectibledefinition" to "service_role";

grant trigger on table "public"."destinycollectibledefinition" to "service_role";

grant truncate on table "public"."destinycollectibledefinition" to "service_role";

grant update on table "public"."destinycollectibledefinition" to "service_role";

grant delete on table "public"."destinydamagetypedefinition" to "anon";

grant insert on table "public"."destinydamagetypedefinition" to "anon";

grant references on table "public"."destinydamagetypedefinition" to "anon";

grant select on table "public"."destinydamagetypedefinition" to "anon";

grant trigger on table "public"."destinydamagetypedefinition" to "anon";

grant truncate on table "public"."destinydamagetypedefinition" to "anon";

grant update on table "public"."destinydamagetypedefinition" to "anon";

grant delete on table "public"."destinydamagetypedefinition" to "authenticated";

grant insert on table "public"."destinydamagetypedefinition" to "authenticated";

grant references on table "public"."destinydamagetypedefinition" to "authenticated";

grant select on table "public"."destinydamagetypedefinition" to "authenticated";

grant trigger on table "public"."destinydamagetypedefinition" to "authenticated";

grant truncate on table "public"."destinydamagetypedefinition" to "authenticated";

grant update on table "public"."destinydamagetypedefinition" to "authenticated";

grant delete on table "public"."destinydamagetypedefinition" to "service_role";

grant insert on table "public"."destinydamagetypedefinition" to "service_role";

grant references on table "public"."destinydamagetypedefinition" to "service_role";

grant select on table "public"."destinydamagetypedefinition" to "service_role";

grant trigger on table "public"."destinydamagetypedefinition" to "service_role";

grant truncate on table "public"."destinydamagetypedefinition" to "service_role";

grant update on table "public"."destinydamagetypedefinition" to "service_role";

grant delete on table "public"."destinydestinationdefinition" to "anon";

grant insert on table "public"."destinydestinationdefinition" to "anon";

grant references on table "public"."destinydestinationdefinition" to "anon";

grant select on table "public"."destinydestinationdefinition" to "anon";

grant trigger on table "public"."destinydestinationdefinition" to "anon";

grant truncate on table "public"."destinydestinationdefinition" to "anon";

grant update on table "public"."destinydestinationdefinition" to "anon";

grant delete on table "public"."destinydestinationdefinition" to "authenticated";

grant insert on table "public"."destinydestinationdefinition" to "authenticated";

grant references on table "public"."destinydestinationdefinition" to "authenticated";

grant select on table "public"."destinydestinationdefinition" to "authenticated";

grant trigger on table "public"."destinydestinationdefinition" to "authenticated";

grant truncate on table "public"."destinydestinationdefinition" to "authenticated";

grant update on table "public"."destinydestinationdefinition" to "authenticated";

grant delete on table "public"."destinydestinationdefinition" to "service_role";

grant insert on table "public"."destinydestinationdefinition" to "service_role";

grant references on table "public"."destinydestinationdefinition" to "service_role";

grant select on table "public"."destinydestinationdefinition" to "service_role";

grant trigger on table "public"."destinydestinationdefinition" to "service_role";

grant truncate on table "public"."destinydestinationdefinition" to "service_role";

grant update on table "public"."destinydestinationdefinition" to "service_role";

grant delete on table "public"."destinyfactiondefinition" to "anon";

grant insert on table "public"."destinyfactiondefinition" to "anon";

grant references on table "public"."destinyfactiondefinition" to "anon";

grant select on table "public"."destinyfactiondefinition" to "anon";

grant trigger on table "public"."destinyfactiondefinition" to "anon";

grant truncate on table "public"."destinyfactiondefinition" to "anon";

grant update on table "public"."destinyfactiondefinition" to "anon";

grant delete on table "public"."destinyfactiondefinition" to "authenticated";

grant insert on table "public"."destinyfactiondefinition" to "authenticated";

grant references on table "public"."destinyfactiondefinition" to "authenticated";

grant select on table "public"."destinyfactiondefinition" to "authenticated";

grant trigger on table "public"."destinyfactiondefinition" to "authenticated";

grant truncate on table "public"."destinyfactiondefinition" to "authenticated";

grant update on table "public"."destinyfactiondefinition" to "authenticated";

grant delete on table "public"."destinyfactiondefinition" to "service_role";

grant insert on table "public"."destinyfactiondefinition" to "service_role";

grant references on table "public"."destinyfactiondefinition" to "service_role";

grant select on table "public"."destinyfactiondefinition" to "service_role";

grant trigger on table "public"."destinyfactiondefinition" to "service_role";

grant truncate on table "public"."destinyfactiondefinition" to "service_role";

grant update on table "public"."destinyfactiondefinition" to "service_role";

grant delete on table "public"."destinygenderdefinition" to "anon";

grant insert on table "public"."destinygenderdefinition" to "anon";

grant references on table "public"."destinygenderdefinition" to "anon";

grant select on table "public"."destinygenderdefinition" to "anon";

grant trigger on table "public"."destinygenderdefinition" to "anon";

grant truncate on table "public"."destinygenderdefinition" to "anon";

grant update on table "public"."destinygenderdefinition" to "anon";

grant delete on table "public"."destinygenderdefinition" to "authenticated";

grant insert on table "public"."destinygenderdefinition" to "authenticated";

grant references on table "public"."destinygenderdefinition" to "authenticated";

grant select on table "public"."destinygenderdefinition" to "authenticated";

grant trigger on table "public"."destinygenderdefinition" to "authenticated";

grant truncate on table "public"."destinygenderdefinition" to "authenticated";

grant update on table "public"."destinygenderdefinition" to "authenticated";

grant delete on table "public"."destinygenderdefinition" to "service_role";

grant insert on table "public"."destinygenderdefinition" to "service_role";

grant references on table "public"."destinygenderdefinition" to "service_role";

grant select on table "public"."destinygenderdefinition" to "service_role";

grant trigger on table "public"."destinygenderdefinition" to "service_role";

grant truncate on table "public"."destinygenderdefinition" to "service_role";

grant update on table "public"."destinygenderdefinition" to "service_role";

grant delete on table "public"."destinyinventorybucketdefinition" to "anon";

grant insert on table "public"."destinyinventorybucketdefinition" to "anon";

grant references on table "public"."destinyinventorybucketdefinition" to "anon";

grant select on table "public"."destinyinventorybucketdefinition" to "anon";

grant trigger on table "public"."destinyinventorybucketdefinition" to "anon";

grant truncate on table "public"."destinyinventorybucketdefinition" to "anon";

grant update on table "public"."destinyinventorybucketdefinition" to "anon";

grant delete on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant insert on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant references on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant select on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant trigger on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant truncate on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant update on table "public"."destinyinventorybucketdefinition" to "authenticated";

grant delete on table "public"."destinyinventorybucketdefinition" to "service_role";

grant insert on table "public"."destinyinventorybucketdefinition" to "service_role";

grant references on table "public"."destinyinventorybucketdefinition" to "service_role";

grant select on table "public"."destinyinventorybucketdefinition" to "service_role";

grant trigger on table "public"."destinyinventorybucketdefinition" to "service_role";

grant truncate on table "public"."destinyinventorybucketdefinition" to "service_role";

grant update on table "public"."destinyinventorybucketdefinition" to "service_role";

grant delete on table "public"."destinyinventoryitemdefinition" to "anon";

grant insert on table "public"."destinyinventoryitemdefinition" to "anon";

grant references on table "public"."destinyinventoryitemdefinition" to "anon";

grant select on table "public"."destinyinventoryitemdefinition" to "anon";

grant trigger on table "public"."destinyinventoryitemdefinition" to "anon";

grant truncate on table "public"."destinyinventoryitemdefinition" to "anon";

grant update on table "public"."destinyinventoryitemdefinition" to "anon";

grant delete on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant insert on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant references on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant select on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant trigger on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant truncate on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant update on table "public"."destinyinventoryitemdefinition" to "authenticated";

grant delete on table "public"."destinyinventoryitemdefinition" to "service_role";

grant insert on table "public"."destinyinventoryitemdefinition" to "service_role";

grant references on table "public"."destinyinventoryitemdefinition" to "service_role";

grant select on table "public"."destinyinventoryitemdefinition" to "service_role";

grant trigger on table "public"."destinyinventoryitemdefinition" to "service_role";

grant truncate on table "public"."destinyinventoryitemdefinition" to "service_role";

grant update on table "public"."destinyinventoryitemdefinition" to "service_role";

grant delete on table "public"."destinymetricdefinition" to "anon";

grant insert on table "public"."destinymetricdefinition" to "anon";

grant references on table "public"."destinymetricdefinition" to "anon";

grant select on table "public"."destinymetricdefinition" to "anon";

grant trigger on table "public"."destinymetricdefinition" to "anon";

grant truncate on table "public"."destinymetricdefinition" to "anon";

grant update on table "public"."destinymetricdefinition" to "anon";

grant delete on table "public"."destinymetricdefinition" to "authenticated";

grant insert on table "public"."destinymetricdefinition" to "authenticated";

grant references on table "public"."destinymetricdefinition" to "authenticated";

grant select on table "public"."destinymetricdefinition" to "authenticated";

grant trigger on table "public"."destinymetricdefinition" to "authenticated";

grant truncate on table "public"."destinymetricdefinition" to "authenticated";

grant update on table "public"."destinymetricdefinition" to "authenticated";

grant delete on table "public"."destinymetricdefinition" to "service_role";

grant insert on table "public"."destinymetricdefinition" to "service_role";

grant references on table "public"."destinymetricdefinition" to "service_role";

grant select on table "public"."destinymetricdefinition" to "service_role";

grant trigger on table "public"."destinymetricdefinition" to "service_role";

grant truncate on table "public"."destinymetricdefinition" to "service_role";

grant update on table "public"."destinymetricdefinition" to "service_role";

grant delete on table "public"."destinyobjectivedefinition" to "anon";

grant insert on table "public"."destinyobjectivedefinition" to "anon";

grant references on table "public"."destinyobjectivedefinition" to "anon";

grant select on table "public"."destinyobjectivedefinition" to "anon";

grant trigger on table "public"."destinyobjectivedefinition" to "anon";

grant truncate on table "public"."destinyobjectivedefinition" to "anon";

grant update on table "public"."destinyobjectivedefinition" to "anon";

grant delete on table "public"."destinyobjectivedefinition" to "authenticated";

grant insert on table "public"."destinyobjectivedefinition" to "authenticated";

grant references on table "public"."destinyobjectivedefinition" to "authenticated";

grant select on table "public"."destinyobjectivedefinition" to "authenticated";

grant trigger on table "public"."destinyobjectivedefinition" to "authenticated";

grant truncate on table "public"."destinyobjectivedefinition" to "authenticated";

grant update on table "public"."destinyobjectivedefinition" to "authenticated";

grant delete on table "public"."destinyobjectivedefinition" to "service_role";

grant insert on table "public"."destinyobjectivedefinition" to "service_role";

grant references on table "public"."destinyobjectivedefinition" to "service_role";

grant select on table "public"."destinyobjectivedefinition" to "service_role";

grant trigger on table "public"."destinyobjectivedefinition" to "service_role";

grant truncate on table "public"."destinyobjectivedefinition" to "service_role";

grant update on table "public"."destinyobjectivedefinition" to "service_role";

grant delete on table "public"."destinyplacedefinition" to "anon";

grant insert on table "public"."destinyplacedefinition" to "anon";

grant references on table "public"."destinyplacedefinition" to "anon";

grant select on table "public"."destinyplacedefinition" to "anon";

grant trigger on table "public"."destinyplacedefinition" to "anon";

grant truncate on table "public"."destinyplacedefinition" to "anon";

grant update on table "public"."destinyplacedefinition" to "anon";

grant delete on table "public"."destinyplacedefinition" to "authenticated";

grant insert on table "public"."destinyplacedefinition" to "authenticated";

grant references on table "public"."destinyplacedefinition" to "authenticated";

grant select on table "public"."destinyplacedefinition" to "authenticated";

grant trigger on table "public"."destinyplacedefinition" to "authenticated";

grant truncate on table "public"."destinyplacedefinition" to "authenticated";

grant update on table "public"."destinyplacedefinition" to "authenticated";

grant delete on table "public"."destinyplacedefinition" to "service_role";

grant insert on table "public"."destinyplacedefinition" to "service_role";

grant references on table "public"."destinyplacedefinition" to "service_role";

grant select on table "public"."destinyplacedefinition" to "service_role";

grant trigger on table "public"."destinyplacedefinition" to "service_role";

grant truncate on table "public"."destinyplacedefinition" to "service_role";

grant update on table "public"."destinyplacedefinition" to "service_role";

grant delete on table "public"."destinyplugsetdefinition" to "anon";

grant insert on table "public"."destinyplugsetdefinition" to "anon";

grant references on table "public"."destinyplugsetdefinition" to "anon";

grant select on table "public"."destinyplugsetdefinition" to "anon";

grant trigger on table "public"."destinyplugsetdefinition" to "anon";

grant truncate on table "public"."destinyplugsetdefinition" to "anon";

grant update on table "public"."destinyplugsetdefinition" to "anon";

grant delete on table "public"."destinyplugsetdefinition" to "authenticated";

grant insert on table "public"."destinyplugsetdefinition" to "authenticated";

grant references on table "public"."destinyplugsetdefinition" to "authenticated";

grant select on table "public"."destinyplugsetdefinition" to "authenticated";

grant trigger on table "public"."destinyplugsetdefinition" to "authenticated";

grant truncate on table "public"."destinyplugsetdefinition" to "authenticated";

grant update on table "public"."destinyplugsetdefinition" to "authenticated";

grant delete on table "public"."destinyplugsetdefinition" to "service_role";

grant insert on table "public"."destinyplugsetdefinition" to "service_role";

grant references on table "public"."destinyplugsetdefinition" to "service_role";

grant select on table "public"."destinyplugsetdefinition" to "service_role";

grant trigger on table "public"."destinyplugsetdefinition" to "service_role";

grant truncate on table "public"."destinyplugsetdefinition" to "service_role";

grant update on table "public"."destinyplugsetdefinition" to "service_role";

grant delete on table "public"."destinypresentationnodedefinition" to "anon";

grant insert on table "public"."destinypresentationnodedefinition" to "anon";

grant references on table "public"."destinypresentationnodedefinition" to "anon";

grant select on table "public"."destinypresentationnodedefinition" to "anon";

grant trigger on table "public"."destinypresentationnodedefinition" to "anon";

grant truncate on table "public"."destinypresentationnodedefinition" to "anon";

grant update on table "public"."destinypresentationnodedefinition" to "anon";

grant delete on table "public"."destinypresentationnodedefinition" to "authenticated";

grant insert on table "public"."destinypresentationnodedefinition" to "authenticated";

grant references on table "public"."destinypresentationnodedefinition" to "authenticated";

grant select on table "public"."destinypresentationnodedefinition" to "authenticated";

grant trigger on table "public"."destinypresentationnodedefinition" to "authenticated";

grant truncate on table "public"."destinypresentationnodedefinition" to "authenticated";

grant update on table "public"."destinypresentationnodedefinition" to "authenticated";

grant delete on table "public"."destinypresentationnodedefinition" to "service_role";

grant insert on table "public"."destinypresentationnodedefinition" to "service_role";

grant references on table "public"."destinypresentationnodedefinition" to "service_role";

grant select on table "public"."destinypresentationnodedefinition" to "service_role";

grant trigger on table "public"."destinypresentationnodedefinition" to "service_role";

grant truncate on table "public"."destinypresentationnodedefinition" to "service_role";

grant update on table "public"."destinypresentationnodedefinition" to "service_role";

grant delete on table "public"."destinyprogressiondefinition" to "anon";

grant insert on table "public"."destinyprogressiondefinition" to "anon";

grant references on table "public"."destinyprogressiondefinition" to "anon";

grant select on table "public"."destinyprogressiondefinition" to "anon";

grant trigger on table "public"."destinyprogressiondefinition" to "anon";

grant truncate on table "public"."destinyprogressiondefinition" to "anon";

grant update on table "public"."destinyprogressiondefinition" to "anon";

grant delete on table "public"."destinyprogressiondefinition" to "authenticated";

grant insert on table "public"."destinyprogressiondefinition" to "authenticated";

grant references on table "public"."destinyprogressiondefinition" to "authenticated";

grant select on table "public"."destinyprogressiondefinition" to "authenticated";

grant trigger on table "public"."destinyprogressiondefinition" to "authenticated";

grant truncate on table "public"."destinyprogressiondefinition" to "authenticated";

grant update on table "public"."destinyprogressiondefinition" to "authenticated";

grant delete on table "public"."destinyprogressiondefinition" to "service_role";

grant insert on table "public"."destinyprogressiondefinition" to "service_role";

grant references on table "public"."destinyprogressiondefinition" to "service_role";

grant select on table "public"."destinyprogressiondefinition" to "service_role";

grant trigger on table "public"."destinyprogressiondefinition" to "service_role";

grant truncate on table "public"."destinyprogressiondefinition" to "service_role";

grant update on table "public"."destinyprogressiondefinition" to "service_role";

grant delete on table "public"."destinyracedefinition" to "anon";

grant insert on table "public"."destinyracedefinition" to "anon";

grant references on table "public"."destinyracedefinition" to "anon";

grant select on table "public"."destinyracedefinition" to "anon";

grant trigger on table "public"."destinyracedefinition" to "anon";

grant truncate on table "public"."destinyracedefinition" to "anon";

grant update on table "public"."destinyracedefinition" to "anon";

grant delete on table "public"."destinyracedefinition" to "authenticated";

grant insert on table "public"."destinyracedefinition" to "authenticated";

grant references on table "public"."destinyracedefinition" to "authenticated";

grant select on table "public"."destinyracedefinition" to "authenticated";

grant trigger on table "public"."destinyracedefinition" to "authenticated";

grant truncate on table "public"."destinyracedefinition" to "authenticated";

grant update on table "public"."destinyracedefinition" to "authenticated";

grant delete on table "public"."destinyracedefinition" to "service_role";

grant insert on table "public"."destinyracedefinition" to "service_role";

grant references on table "public"."destinyracedefinition" to "service_role";

grant select on table "public"."destinyracedefinition" to "service_role";

grant trigger on table "public"."destinyracedefinition" to "service_role";

grant truncate on table "public"."destinyracedefinition" to "service_role";

grant update on table "public"."destinyracedefinition" to "service_role";

grant delete on table "public"."destinyrecorddefinition" to "anon";

grant insert on table "public"."destinyrecorddefinition" to "anon";

grant references on table "public"."destinyrecorddefinition" to "anon";

grant select on table "public"."destinyrecorddefinition" to "anon";

grant trigger on table "public"."destinyrecorddefinition" to "anon";

grant truncate on table "public"."destinyrecorddefinition" to "anon";

grant update on table "public"."destinyrecorddefinition" to "anon";

grant delete on table "public"."destinyrecorddefinition" to "authenticated";

grant insert on table "public"."destinyrecorddefinition" to "authenticated";

grant references on table "public"."destinyrecorddefinition" to "authenticated";

grant select on table "public"."destinyrecorddefinition" to "authenticated";

grant trigger on table "public"."destinyrecorddefinition" to "authenticated";

grant truncate on table "public"."destinyrecorddefinition" to "authenticated";

grant update on table "public"."destinyrecorddefinition" to "authenticated";

grant delete on table "public"."destinyrecorddefinition" to "service_role";

grant insert on table "public"."destinyrecorddefinition" to "service_role";

grant references on table "public"."destinyrecorddefinition" to "service_role";

grant select on table "public"."destinyrecorddefinition" to "service_role";

grant trigger on table "public"."destinyrecorddefinition" to "service_role";

grant truncate on table "public"."destinyrecorddefinition" to "service_role";

grant update on table "public"."destinyrecorddefinition" to "service_role";

grant delete on table "public"."destinysandboxperkdefinition" to "anon";

grant insert on table "public"."destinysandboxperkdefinition" to "anon";

grant references on table "public"."destinysandboxperkdefinition" to "anon";

grant select on table "public"."destinysandboxperkdefinition" to "anon";

grant trigger on table "public"."destinysandboxperkdefinition" to "anon";

grant truncate on table "public"."destinysandboxperkdefinition" to "anon";

grant update on table "public"."destinysandboxperkdefinition" to "anon";

grant delete on table "public"."destinysandboxperkdefinition" to "authenticated";

grant insert on table "public"."destinysandboxperkdefinition" to "authenticated";

grant references on table "public"."destinysandboxperkdefinition" to "authenticated";

grant select on table "public"."destinysandboxperkdefinition" to "authenticated";

grant trigger on table "public"."destinysandboxperkdefinition" to "authenticated";

grant truncate on table "public"."destinysandboxperkdefinition" to "authenticated";

grant update on table "public"."destinysandboxperkdefinition" to "authenticated";

grant delete on table "public"."destinysandboxperkdefinition" to "service_role";

grant insert on table "public"."destinysandboxperkdefinition" to "service_role";

grant references on table "public"."destinysandboxperkdefinition" to "service_role";

grant select on table "public"."destinysandboxperkdefinition" to "service_role";

grant trigger on table "public"."destinysandboxperkdefinition" to "service_role";

grant truncate on table "public"."destinysandboxperkdefinition" to "service_role";

grant update on table "public"."destinysandboxperkdefinition" to "service_role";

grant delete on table "public"."destinyseasondefinition" to "anon";

grant insert on table "public"."destinyseasondefinition" to "anon";

grant references on table "public"."destinyseasondefinition" to "anon";

grant select on table "public"."destinyseasondefinition" to "anon";

grant trigger on table "public"."destinyseasondefinition" to "anon";

grant truncate on table "public"."destinyseasondefinition" to "anon";

grant update on table "public"."destinyseasondefinition" to "anon";

grant delete on table "public"."destinyseasondefinition" to "authenticated";

grant insert on table "public"."destinyseasondefinition" to "authenticated";

grant references on table "public"."destinyseasondefinition" to "authenticated";

grant select on table "public"."destinyseasondefinition" to "authenticated";

grant trigger on table "public"."destinyseasondefinition" to "authenticated";

grant truncate on table "public"."destinyseasondefinition" to "authenticated";

grant update on table "public"."destinyseasondefinition" to "authenticated";

grant delete on table "public"."destinyseasondefinition" to "service_role";

grant insert on table "public"."destinyseasondefinition" to "service_role";

grant references on table "public"."destinyseasondefinition" to "service_role";

grant select on table "public"."destinyseasondefinition" to "service_role";

grant trigger on table "public"."destinyseasondefinition" to "service_role";

grant truncate on table "public"."destinyseasondefinition" to "service_role";

grant update on table "public"."destinyseasondefinition" to "service_role";

grant delete on table "public"."destinysocketcategorydefinition" to "anon";

grant insert on table "public"."destinysocketcategorydefinition" to "anon";

grant references on table "public"."destinysocketcategorydefinition" to "anon";

grant select on table "public"."destinysocketcategorydefinition" to "anon";

grant trigger on table "public"."destinysocketcategorydefinition" to "anon";

grant truncate on table "public"."destinysocketcategorydefinition" to "anon";

grant update on table "public"."destinysocketcategorydefinition" to "anon";

grant delete on table "public"."destinysocketcategorydefinition" to "authenticated";

grant insert on table "public"."destinysocketcategorydefinition" to "authenticated";

grant references on table "public"."destinysocketcategorydefinition" to "authenticated";

grant select on table "public"."destinysocketcategorydefinition" to "authenticated";

grant trigger on table "public"."destinysocketcategorydefinition" to "authenticated";

grant truncate on table "public"."destinysocketcategorydefinition" to "authenticated";

grant update on table "public"."destinysocketcategorydefinition" to "authenticated";

grant delete on table "public"."destinysocketcategorydefinition" to "service_role";

grant insert on table "public"."destinysocketcategorydefinition" to "service_role";

grant references on table "public"."destinysocketcategorydefinition" to "service_role";

grant select on table "public"."destinysocketcategorydefinition" to "service_role";

grant trigger on table "public"."destinysocketcategorydefinition" to "service_role";

grant truncate on table "public"."destinysocketcategorydefinition" to "service_role";

grant update on table "public"."destinysocketcategorydefinition" to "service_role";

grant delete on table "public"."destinysockettypedefinition" to "anon";

grant insert on table "public"."destinysockettypedefinition" to "anon";

grant references on table "public"."destinysockettypedefinition" to "anon";

grant select on table "public"."destinysockettypedefinition" to "anon";

grant trigger on table "public"."destinysockettypedefinition" to "anon";

grant truncate on table "public"."destinysockettypedefinition" to "anon";

grant update on table "public"."destinysockettypedefinition" to "anon";

grant delete on table "public"."destinysockettypedefinition" to "authenticated";

grant insert on table "public"."destinysockettypedefinition" to "authenticated";

grant references on table "public"."destinysockettypedefinition" to "authenticated";

grant select on table "public"."destinysockettypedefinition" to "authenticated";

grant trigger on table "public"."destinysockettypedefinition" to "authenticated";

grant truncate on table "public"."destinysockettypedefinition" to "authenticated";

grant update on table "public"."destinysockettypedefinition" to "authenticated";

grant delete on table "public"."destinysockettypedefinition" to "service_role";

grant insert on table "public"."destinysockettypedefinition" to "service_role";

grant references on table "public"."destinysockettypedefinition" to "service_role";

grant select on table "public"."destinysockettypedefinition" to "service_role";

grant trigger on table "public"."destinysockettypedefinition" to "service_role";

grant truncate on table "public"."destinysockettypedefinition" to "service_role";

grant update on table "public"."destinysockettypedefinition" to "service_role";

grant delete on table "public"."destinystatdefinition" to "anon";

grant insert on table "public"."destinystatdefinition" to "anon";

grant references on table "public"."destinystatdefinition" to "anon";

grant select on table "public"."destinystatdefinition" to "anon";

grant trigger on table "public"."destinystatdefinition" to "anon";

grant truncate on table "public"."destinystatdefinition" to "anon";

grant update on table "public"."destinystatdefinition" to "anon";

grant delete on table "public"."destinystatdefinition" to "authenticated";

grant insert on table "public"."destinystatdefinition" to "authenticated";

grant references on table "public"."destinystatdefinition" to "authenticated";

grant select on table "public"."destinystatdefinition" to "authenticated";

grant trigger on table "public"."destinystatdefinition" to "authenticated";

grant truncate on table "public"."destinystatdefinition" to "authenticated";

grant update on table "public"."destinystatdefinition" to "authenticated";

grant delete on table "public"."destinystatdefinition" to "service_role";

grant insert on table "public"."destinystatdefinition" to "service_role";

grant references on table "public"."destinystatdefinition" to "service_role";

grant select on table "public"."destinystatdefinition" to "service_role";

grant trigger on table "public"."destinystatdefinition" to "service_role";

grant truncate on table "public"."destinystatdefinition" to "service_role";

grant update on table "public"."destinystatdefinition" to "service_role";

grant delete on table "public"."destinytraitdefinition" to "anon";

grant insert on table "public"."destinytraitdefinition" to "anon";

grant references on table "public"."destinytraitdefinition" to "anon";

grant select on table "public"."destinytraitdefinition" to "anon";

grant trigger on table "public"."destinytraitdefinition" to "anon";

grant truncate on table "public"."destinytraitdefinition" to "anon";

grant update on table "public"."destinytraitdefinition" to "anon";

grant delete on table "public"."destinytraitdefinition" to "authenticated";

grant insert on table "public"."destinytraitdefinition" to "authenticated";

grant references on table "public"."destinytraitdefinition" to "authenticated";

grant select on table "public"."destinytraitdefinition" to "authenticated";

grant trigger on table "public"."destinytraitdefinition" to "authenticated";

grant truncate on table "public"."destinytraitdefinition" to "authenticated";

grant update on table "public"."destinytraitdefinition" to "authenticated";

grant delete on table "public"."destinytraitdefinition" to "service_role";

grant insert on table "public"."destinytraitdefinition" to "service_role";

grant references on table "public"."destinytraitdefinition" to "service_role";

grant select on table "public"."destinytraitdefinition" to "service_role";

grant trigger on table "public"."destinytraitdefinition" to "service_role";

grant truncate on table "public"."destinytraitdefinition" to "service_role";

grant update on table "public"."destinytraitdefinition" to "service_role";

grant delete on table "public"."destinyvendordefinition" to "anon";

grant insert on table "public"."destinyvendordefinition" to "anon";

grant references on table "public"."destinyvendordefinition" to "anon";

grant select on table "public"."destinyvendordefinition" to "anon";

grant trigger on table "public"."destinyvendordefinition" to "anon";

grant truncate on table "public"."destinyvendordefinition" to "anon";

grant update on table "public"."destinyvendordefinition" to "anon";

grant delete on table "public"."destinyvendordefinition" to "authenticated";

grant insert on table "public"."destinyvendordefinition" to "authenticated";

grant references on table "public"."destinyvendordefinition" to "authenticated";

grant select on table "public"."destinyvendordefinition" to "authenticated";

grant trigger on table "public"."destinyvendordefinition" to "authenticated";

grant truncate on table "public"."destinyvendordefinition" to "authenticated";

grant update on table "public"."destinyvendordefinition" to "authenticated";

grant delete on table "public"."destinyvendordefinition" to "service_role";

grant insert on table "public"."destinyvendordefinition" to "service_role";

grant references on table "public"."destinyvendordefinition" to "service_role";

grant select on table "public"."destinyvendordefinition" to "service_role";

grant trigger on table "public"."destinyvendordefinition" to "service_role";

grant truncate on table "public"."destinyvendordefinition" to "service_role";

grant update on table "public"."destinyvendordefinition" to "service_role";


