-- v2.0.4: account system (detail-4)
-- Requires Supabase Auth (auth.users). Run after 002_work_progress.sql.

-- 1. nullable user_id on saves — guest saves have user_id IS NULL
alter table public.saves
  add column if not exists user_id uuid null references auth.users (id) on delete set null;

create index if not exists saves_user_id_idx on public.saves (user_id);
create index if not exists saves_user_work_idx on public.saves (user_id, work_id);

-- 2. short_play_records — one row per completed short-form play for logged-in users
create table if not exists public.short_play_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  work_id text not null references public.works (id) on delete cascade,
  outcome text not null check (outcome in ('win', 'lose', 'timeout')),
  completed_at timestamptz not null default now()
);

create index if not exists short_play_records_user_idx on public.short_play_records (user_id, completed_at desc);

alter table public.short_play_records enable row level security;

-- 3. user_work_progress — per-user discovered endings for long-form works
create table if not exists public.user_work_progress (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  work_id text not null references public.works (id) on delete cascade,
  discovered_endings jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now(),
  constraint user_work_progress_unique unique (user_id, work_id)
);

create index if not exists user_work_progress_user_idx on public.user_work_progress (user_id);

drop trigger if exists user_work_progress_set_updated_at on public.user_work_progress;
create trigger user_work_progress_set_updated_at
  before update on public.user_work_progress
  for each row execute function public.set_updated_at();

alter table public.user_work_progress enable row level security;
