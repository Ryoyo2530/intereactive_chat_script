-- v2.0.3 product layer: cross-run discovered endings per work
-- Safe to run after 001_works_chapters_saves.sql

alter table public.saves
  add column if not exists visited_chapter_ids jsonb not null default '[]'::jsonb;

alter table public.saves
  add column if not exists had_branch_choice boolean not null default false;

create table if not exists public.work_progress (
  work_id text primary key references public.works (id) on delete cascade,
  discovered_endings jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

drop trigger if exists work_progress_set_updated_at on public.work_progress;
create trigger work_progress_set_updated_at
  before update on public.work_progress
  for each row execute function public.set_updated_at();

alter table public.work_progress enable row level security;
