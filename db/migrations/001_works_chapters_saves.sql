-- v2.0.1 / v2.0.2: content assets persistence (works / chapters / saves)
-- Run this in the Supabase SQL editor (or via supabase db push) before migrating scripts.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- works (作品级)
-- ---------------------------------------------------------------------------
create table if not exists public.works (
  id text primary key,
  type text not null check (type in ('short_form', 'long_form')),
  title text not null,
  origin_tag text not null default '',
  theme_tags jsonb not null default '[]'::jsonb,
  teaser text not null default '',
  player_role_hint text not null default '',
  estimated_turns_hint text not null default '',
  stats_schema jsonb not null default '{}'::jsonb,
  chapter_ids jsonb not null default '[]'::jsonb,
  entry_chapter_id text not null,
  status text not null default 'published' check (status in ('draft', 'published')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists works_status_idx on public.works (status);
create index if not exists works_type_idx on public.works (type);

-- ---------------------------------------------------------------------------
-- chapters (章节级)
-- ---------------------------------------------------------------------------
create table if not exists public.chapters (
  id text primary key,
  work_id text not null references public.works (id) on delete cascade,
  title text not null default '',
  background text not null default '',
  ai_character jsonb not null default '{}'::jsonb,
  player_character jsonb not null default '{}'::jsonb,
  opening_line text not null default '',
  max_turns int not null default 12,
  key_points jsonb not null default '[]'::jsonb,
  pitfalls jsonb not null default '[]'::jsonb,
  flags_read jsonb not null default '[]'::jsonb,
  flags_write jsonb not null default '[]'::jsonb,
  -- short_form terminal placeholder: {type, win_condition, lose_condition}
  -- long_form (detail-2): hard_condition / ai_choice exits
  exits jsonb not null default '[]'::jsonb,
  -- v1 fields not in the core chapter columns (objective, briefing, echo_phrases, …)
  extras jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists chapters_work_id_idx on public.chapters (work_id);

-- ---------------------------------------------------------------------------
-- saves (存档；短局场景下等价于 session 持久化预留)
-- ---------------------------------------------------------------------------
create table if not exists public.saves (
  id uuid primary key default gen_random_uuid(),
  work_id text not null references public.works (id) on delete cascade,
  current_chapter_id text not null,
  current_turn int not null default 0,
  stats jsonb not null default '{}'::jsonb,
  flags jsonb not null default '{}'::jsonb,
  chapter_summaries jsonb not null default '[]'::jsonb,
  hit_key_point_ids jsonb not null default '[]'::jsonb,
  hit_pitfall_ids jsonb not null default '[]'::jsonb,
  conversation_history jsonb not null default '[]'::jsonb,
  game_over boolean not null default false,
  outcome text null check (outcome is null or outcome in ('win', 'lose')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists saves_work_id_idx on public.saves (work_id);
create index if not exists saves_updated_at_idx on public.saves (updated_at desc);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists works_set_updated_at on public.works;
create trigger works_set_updated_at
  before update on public.works
  for each row execute function public.set_updated_at();

drop trigger if exists chapters_set_updated_at on public.chapters;
create trigger chapters_set_updated_at
  before update on public.chapters
  for each row execute function public.set_updated_at();

drop trigger if exists saves_set_updated_at on public.saves;
create trigger saves_set_updated_at
  before update on public.saves
  for each row execute function public.set_updated_at();

-- Backend uses the service role key (bypasses RLS). Enable RLS with no
-- public policies so anon/authenticated clients cannot read or write content.
alter table public.works enable row level security;
alter table public.chapters enable row level security;
alter table public.saves enable row level security;
