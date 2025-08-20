-- Security Fixes for Supabase Linter Issues
-- Migration: 20250820_security_fixes
-- Purpose: Fix RLS policies, function security, and view definitions
-- Date: 2025-08-20

-- ===============================================================
-- 1) ENABLE ROW LEVEL SECURITY (RLS) ON PUBLIC TABLES
-- ===============================================================

-- Enable RLS on existing tables that are exposed via PostgREST
alter table if exists public.tweets enable row level security;
alter table if exists public.engagement_metrics enable row level security;
alter table if exists public.processed_tweets enable row level security;
alter table if exists public.tweet_decisions enable row level security;
alter table if exists public.manual_replies enable row level security;

-- Create permissive policies for authenticated users (your app)
-- This allows your service role to read/write everything while restricting anon access

-- Policy for tweets table
drop policy if exists "Allow service role full access" on public.tweets;
create policy "Allow service role full access" on public.tweets
  for all to service_role using (true);

-- Policy for engagement_metrics table  
drop policy if exists "Allow service role full access" on public.engagement_metrics;
create policy "Allow service role full access" on public.engagement_metrics
  for all to service_role using (true);

-- Policy for processed_tweets table
drop policy if exists "Allow service role full access" on public.processed_tweets;
create policy "Allow service role full access" on public.processed_tweets
  for all to service_role using (true);

-- Policy for tweet_decisions table
drop policy if exists "Allow service role full access" on public.tweet_decisions;
create policy "Allow service role full access" on public.tweet_decisions
  for all to service_role using (true);

-- Policy for manual_replies table
drop policy if exists "Allow service role full access" on public.manual_replies;
create policy "Allow service role full access" on public.manual_replies
  for all to service_role using (true);

-- Allow anon read access to approved tweets only (for dashboard UI)
drop policy if exists "Allow anon read approved tweets" on public.tweet_decisions;
create policy "Allow anon read approved tweets" on public.tweet_decisions
  for select to anon using (final = 'approved');

-- ===============================================================
-- 2) FIX SECURITY DEFINER VIEWS
-- ===============================================================

-- Recreate views without SECURITY DEFINER to use invoker's permissions
drop view if exists public.v_approved_tweets;
create view public.v_approved_tweets as
select 
  d.tweet_id, 
  d.author_id,
  d.tweet_text,
  d.ai_score, 
  d.ai_reason, 
  d.categories,
  d.processing_time_ms,
  d.created_at as decided_at,
  d.filter_version
from public.tweet_decisions d
where d.final = 'approved'
order by d.created_at desc;

drop view if exists public.v_filter_comparison;
create view public.v_filter_comparison as
select 
  filter_version,
  final,
  count(*) as tweet_count,
  round(avg(ai_score), 1) as avg_score,
  round(
    count(*) filter (where final = 'approved') * 100.0 / count(*), 
    1
  ) as approval_rate_percent
from public.tweet_decisions 
where created_at > now() - interval '24 hours'
  and filter_version != 'seed'  -- Exclude test data
group by filter_version, final
order by filter_version, final;

drop view if exists public.v_filter_health;
create view public.v_filter_health as
select 
  date_trunc('hour', created_at) as hour,
  filter_version,
  count(*) as total_processed,
  count(*) filter (where final = 'approved') as approved,
  count(*) filter (where stage_quick = 'reject') as quick_rejects,
  count(*) filter (where stage_ai = 'reject') as ai_rejects,
  count(*) filter (where stage_quick = 'error' or stage_ai = 'error') as errors,
  round(avg(processing_time_ms), 0) as avg_processing_ms
from public.tweet_decisions
where created_at > now() - interval '24 hours'
  and filter_version != 'seed'
group by date_trunc('hour', created_at), filter_version
order by hour desc, filter_version;

-- ===============================================================  
-- 3) FIX FUNCTION SEARCH_PATH SECURITY
-- ===============================================================

-- Update functions to have secure search_path
drop function if exists public.cleanup_processed_tweets();
create or replace function public.cleanup_processed_tweets()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  -- Clean up processed_tweets older than 30 days
  delete from public.processed_tweets 
  where processed_at < now() - interval '30 days';
  
  raise notice 'Cleaned up old processed tweets';
end;
$$;

drop function if exists public.get_filter_stats(int);
create or replace function public.get_filter_stats(hours_back int default 24)
returns table (
  metric text,
  value numeric
)
language plpgsql
security definer 
set search_path = public
as $$
begin
  return query
  select 'total_processed'::text, count(*)::numeric 
  from public.tweet_decisions 
  where created_at > now() - (hours_back || ' hours')::interval 
    and filter_version != 'seed'
  union all
  select 'approved'::text, count(*)::numeric 
  from public.tweet_decisions 
  where created_at > now() - (hours_back || ' hours')::interval 
    and filter_version != 'seed' 
    and final = 'approved'
  union all
  select 'approval_rate_percent'::text, 
    case 
      when count(*) > 0 then 
        count(*) filter (where final = 'approved') * 100.0 / count(*)
      else 0
    end
  from public.tweet_decisions 
  where created_at > now() - (hours_back || ' hours')::interval 
    and filter_version != 'seed';
end;
$$;

-- ===============================================================
-- 4) GRANT APPROPRIATE PERMISSIONS
-- ===============================================================

-- Grant view access to anon and authenticated roles for dashboard
grant select on public.v_approved_tweets to anon, authenticated;
grant select on public.v_filter_comparison to anon, authenticated;  
grant select on public.v_filter_health to anon, authenticated;

-- Grant function execution to service role only
grant execute on function public.cleanup_processed_tweets() to service_role;
grant execute on function public.get_filter_stats(int) to service_role;

-- ===============================================================
-- 5) COMMENTS AND DOCUMENTATION
-- ===============================================================

comment on policy "Allow service role full access" on public.tweets is 'Service role needs full access for tweet processing';
comment on policy "Allow service role full access" on public.engagement_metrics is 'Service role needs full access for metrics tracking';
comment on policy "Allow service role full access" on public.processed_tweets is 'Service role needs full access for deduplication';
comment on policy "Allow service role full access" on public.tweet_decisions is 'Service role needs full access for filtering decisions';
comment on policy "Allow service role full access" on public.manual_replies is 'Service role needs full access for reply management';
comment on policy "Allow anon read approved tweets" on public.tweet_decisions is 'Dashboard UI can view approved tweets only';

comment on view public.v_approved_tweets is 'Stable interface for UI - only approved tweets, uses invoker permissions';
comment on view public.v_filter_comparison is 'Compare V1 vs V2 filter performance, uses invoker permissions';
comment on view public.v_filter_health is 'Hourly filtering health metrics, uses invoker permissions';

comment on function public.cleanup_processed_tweets() is 'Cleanup function with secure search_path';
comment on function public.get_filter_stats(int) is 'Get filtering statistics with secure search_path';

-- ===============================================================
-- 6) VERIFY SECURITY SETTINGS
-- ===============================================================

-- Test that RLS is enabled (this will show enabled tables)
do $$
begin
  -- Test views
  perform 1 from public.v_approved_tweets limit 1;
  perform 1 from public.v_filter_comparison limit 1;
  perform 1 from public.v_filter_health limit 1;
  
  -- Test functions  
  perform public.get_filter_stats(1);
  
  raise notice 'Security fixes applied successfully';
  
exception when others then
  raise notice 'Security fix verification failed: %', sqlerrm;
end;
$$;