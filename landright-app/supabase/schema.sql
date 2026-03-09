-- CTA-only analytics schema.
-- Run this in the Supabase SQL editor to wipe existing analytics and create the new schema.
-- Then set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend .env.
--
-- Multi-user: Events are isolated by repo_full_name (e.g. owner/repo). Each exported site
-- sends its repo_full_name with every beacon request, so one table serves all users;
-- the agent and analytics always filter by repo_full_name. No user_id column is required
-- for the pipeline. Add user_id or account_id later if you need cross-repo dashboards or billing.
--
-- SimGym: event_source on cta_events allows simulated traffic (robots) to POST to /beacon
-- with event_source='simulated'; cta_by_variant sums all sources so learning works on real + simulated.

-- Drop existing analytics objects (order: views first — they depend on tables — then tables)
drop view if exists public.time_by_variant_by_source;
drop view if exists public.time_by_section;
drop view if exists public.time_by_variant;
drop view if exists public.cta_by_variant_by_source;
drop view if exists public.cta_by_variant;
drop view if exists public.analytics_by_variant;
drop table if exists public.experience_library_entries;
drop table if exists public.adjustment_log;
drop table if exists public.variant_snapshots;
drop table if exists public.time_events;
drop table if exists public.cta_events;
drop table if exists public.analytics_events;

-- CTA-only events (button clicks only; no page views)
create table public.cta_events (
  id uuid primary key default gen_random_uuid(),
  repo_full_name text not null,
  layer text not null,
  variant_id text not null,
  cta_label text,
  cta_id text,
  occurred_at timestamptz not null default now(),
  event_source text not null default 'real' check (event_source in ('real', 'simulated', 'simgym'))
);

create index idx_cta_events_repo_layer_variant
  on public.cta_events (repo_full_name, layer, variant_id);
create index idx_cta_events_occurred_at
  on public.cta_events (occurred_at desc);
create index idx_cta_events_event_source
  on public.cta_events (event_source) where event_source != 'real';

-- View for agent: CTA clicks per variant (all sources combined)
create view public.cta_by_variant as
select
  repo_full_name,
  layer,
  variant_id,
  count(*) as cta_clicks
from public.cta_events
where repo_full_name is not null and layer is not null and variant_id is not null
group by repo_full_name, layer, variant_id;

-- Optional: view per source for filtered analytics (real-only or simulated-only)
create view public.cta_by_variant_by_source as
select
  repo_full_name,
  layer,
  variant_id,
  event_source,
  count(*) as cta_clicks
from public.cta_events
where repo_full_name is not null and layer is not null and variant_id is not null
group by repo_full_name, layer, variant_id, event_source;

-- Time-on-page events (page-level or section-level duration)
create table public.time_events (
  id uuid primary key default gen_random_uuid(),
  repo_full_name text not null,
  layer text not null,
  variant_id text not null,
  event_source text not null default 'real' check (event_source in ('real', 'simulated', 'simgym')),
  occurred_at timestamptz not null default now(),
  duration_seconds numeric not null,
  section_id text
);

create index idx_time_events_repo_layer_variant
  on public.time_events (repo_full_name, layer, variant_id);
create index idx_time_events_occurred_at
  on public.time_events (occurred_at desc);
create index idx_time_events_event_source
  on public.time_events (event_source) where event_source != 'real';

-- View for agent: total time per variant (all sources combined)
create view public.time_by_variant as
select
  repo_full_name,
  layer,
  variant_id,
  coalesce(sum(duration_seconds), 0)::numeric as total_seconds,
  count(*) as event_count
from public.time_events
where repo_full_name is not null and layer is not null and variant_id is not null
group by repo_full_name, layer, variant_id;

-- Optional: view per source for filtered analytics (real-only or simulated-only)
create view public.time_by_variant_by_source as
select
  repo_full_name,
  layer,
  variant_id,
  event_source,
  coalesce(sum(duration_seconds), 0)::numeric as total_seconds,
  count(*) as event_count
from public.time_events
where repo_full_name is not null and layer is not null and variant_id is not null
group by repo_full_name, layer, variant_id, event_source;

-- Section-level time: which parts of the page were viewed (for visibility tracking)
create view public.time_by_section as
select
  repo_full_name,
  layer,
  variant_id,
  section_id,
  coalesce(sum(duration_seconds), 0)::numeric as total_seconds,
  count(*) as event_count
from public.time_events
where repo_full_name is not null and layer is not null and variant_id is not null
  and section_id is not null and section_id != ''
group by repo_full_name, layer, variant_id, section_id;

-- Independent variables per variant (for learning: diff best vs others)
create table public.variant_snapshots (
  id uuid primary key default gen_random_uuid(),
  repo_full_name text not null,
  layer text not null,
  variant_id text not null,
  snapshot_at timestamptz not null default now(),
  source text,
  sections jsonb default '[]',
  ctas jsonb default '[]',
  tailwind_colors jsonb default '[]',
  font_imports jsonb default '[]',
  responsive boolean default false,
  animated boolean default false,
  line_count int
);

create index idx_variant_snapshots_repo_layer_variant
  on public.variant_snapshots (repo_full_name, layer, variant_id);
create index idx_variant_snapshots_repo_layer_at
  on public.variant_snapshots (repo_full_name, layer, snapshot_at desc);

-- Before/after state when agent runs adjust pipeline (for learning: did change help or hurt?)
create table public.adjustment_log (
  id uuid primary key default gen_random_uuid(),
  repo_full_name text not null,
  layer text not null,
  adjusted_at timestamptz not null default now(),
  best_variant_id text not null,
  clicks_before jsonb not null default '{}',
  times_before jsonb default null,
  evaluated boolean not null default false
);

create index idx_adjustment_log_repo_layer
  on public.adjustment_log (repo_full_name, layer, adjusted_at desc);

-- Learned experience entries (agent writes, generation backend reads for source='generation')
create table public.experience_library_entries (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('generation', 'cta', 'data_analyst')),
  entry text not null,
  created_at timestamptz not null default now()
);
create index idx_experience_library_entries_source
  on public.experience_library_entries (source, created_at desc);
