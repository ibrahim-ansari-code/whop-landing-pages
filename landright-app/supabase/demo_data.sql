-- Demo data for Landright analytics (CTA + time-on-page).
-- Run in Supabase SQL editor AFTER schema.sql. Clears existing event/adjustment data, then inserts.
-- Use layer = '1' and variant_id = 'variant-1'..'variant-4' to match backend normalization.

-- Clear all previous data (events and agent-related tables)
delete from public.adjustment_log;
delete from public.variant_snapshots;
delete from public.time_events;
delete from public.cta_events;

-- Repo ibrahim-ansari-code/re
insert into public.cta_events (repo_full_name, layer, variant_id, cta_label, event_source)
select 'ibrahim-ansari-code/re', '1', 'variant-1', 'Get started', 'real'
from generate_series(1, 52) _;
insert into public.cta_events (repo_full_name, layer, variant_id, cta_label, event_source)
select 'ibrahim-ansari-code/re', '1', 'variant-2', 'Get started', 'real'
from generate_series(1, 38) _;
insert into public.cta_events (repo_full_name, layer, variant_id, cta_label, event_source)
select 'ibrahim-ansari-code/re', '1', 'variant-3', 'Sign up', 'real'
from generate_series(1, 22) _;
insert into public.cta_events (repo_full_name, layer, variant_id, cta_label, event_source)
select 'ibrahim-ansari-code/re', '1', 'variant-4', 'Book a call', 'real'
from generate_series(1, 15) _;

-- Time-on-page: variant-1 has most total time, then 2, 3, 4 (matches “winner” for judge)
insert into public.time_events (repo_full_name, layer, variant_id, duration_seconds, event_source)
values
  ('ibrahim-ansari-code/re', '1', 'variant-1', 45.2, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-1', 62.1, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-1', 38.0, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-1', 91.5, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-1', 55.0, 'real');
insert into public.time_events (repo_full_name, layer, variant_id, duration_seconds, event_source)
values
  ('ibrahim-ansari-code/re', '1', 'variant-2', 32.0, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-2', 48.5, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-2', 41.0, 'real');
insert into public.time_events (repo_full_name, layer, variant_id, duration_seconds, event_source)
values
  ('ibrahim-ansari-code/re', '1', 'variant-3', 28.0, 'real'),
  ('ibrahim-ansari-code/re', '1', 'variant-3', 35.2, 'real');
insert into public.time_events (repo_full_name, layer, variant_id, duration_seconds, event_source)
values
  ('ibrahim-ansari-code/re', '1', 'variant-4', 18.5, 'real');

-- Optional: second repo for multi-repo dashboard
insert into public.cta_events (repo_full_name, layer, variant_id, cta_label, event_source)
select 'demo/other-page', '1', 'variant-' || (1 + (i % 4))::text, 'CTA', 'real'
from generate_series(1, 20) i;
insert into public.time_events (repo_full_name, layer, variant_id, duration_seconds, event_source)
select 'demo/other-page', '1', 'variant-' || (1 + (i % 4))::text, 25.0 + (i % 30), 'real'
from generate_series(1, 8) i;

-- Optional: sample adjustment_log rows (agent writes these on push; here for demo / learning step)
-- times_before = total seconds per variant at adjustment time; clicks_before = CTA clicks per variant
insert into public.adjustment_log (repo_full_name, layer, best_variant_id, clicks_before, times_before, evaluated)
values
  (
    'ibrahim-ansari-code/re',
    '1',
    'variant-1',
    '{"variant-1": 52, "variant-2": 38, "variant-3": 22, "variant-4": 15}'::jsonb,
    '{"variant-1": 291.8, "variant-2": 121.5, "variant-3": 63.2, "variant-4": 18.5}'::jsonb,
    false
  );
insert into public.adjustment_log (repo_full_name, layer, best_variant_id, clicks_before, times_before, evaluated)
values
  (
    'demo/other-page',
    '1',
    'variant-1',
    '{"variant-1": 5, "variant-2": 5, "variant-3": 5, "variant-4": 5}'::jsonb,
    '{"variant-1": 120, "variant-2": 95, "variant-3": 88, "variant-4": 82}'::jsonb,
    false
  );
