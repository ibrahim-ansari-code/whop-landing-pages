-- Add section-level time view to an existing Supabase project.
-- Run this in the Supabase SQL editor if you already have time_events and don't want to re-run the full schema.
-- Section visibility: time_events.section_id is populated by POST /beacon-time with section_id; this view aggregates it.

drop view if exists public.time_by_section;
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
