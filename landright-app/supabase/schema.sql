-- CTA-only analytics schema.
-- Run this in the Supabase SQL editor to wipe existing analytics and create the new schema.
-- Then set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend .env.
--
-- Multi-user: Events are isolated by repo_full_name (e.g. owner/repo). Each exported site
-- sends its repo_full_name with every beacon request, so one table serves all users;
-- the agent and analytics always filter by repo_full_name. No user_id column is required
-- for the pipeline. Add user_id or account_id later if you need cross-repo dashboards or billing.

-- Drop existing analytics objects (order: view then table)
drop view if exists public.analytics_by_variant;
drop table if exists public.analytics_events;

-- CTA-only events (button clicks only; no page views)
create table public.cta_events (
  id uuid primary key default gen_random_uuid(),
  repo_full_name text not null,
  layer text not null,
  variant_id text not null,
  cta_label text,
  cta_id text,
  occurred_at timestamptz not null default now()
);

create index idx_cta_events_repo_layer_variant
  on public.cta_events (repo_full_name, layer, variant_id);
create index idx_cta_events_occurred_at
  on public.cta_events (occurred_at desc);

-- View for agent: CTA clicks per variant (for threshold and best-variant logic)
create view public.cta_by_variant as
select
  repo_full_name,
  layer,
  variant_id,
  count(*) as cta_clicks
from public.cta_events
where repo_full_name is not null and layer is not null and variant_id is not null
group by repo_full_name, layer, variant_id;
