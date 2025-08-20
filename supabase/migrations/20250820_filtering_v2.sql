-- Twitter Auto Bot V2 Filtering Infrastructure
-- Migration: 20250820_filtering_v2
-- Purpose: Content filtering, deduplication, and rate limiting
-- Owner: @stacyenot
-- Date: 2025-08-20

-- ===============================================================
-- 1) DEDUPLICATION TABLE (30-day TTL)
-- ===============================================================

create table if not exists public.processed_tweets (
  tweet_id       text primary key,
  author_id      text not null,
  processed_at   timestamptz not null default now()
);

-- Indexes for performance
create index if not exists idx_processed_author_time on public.processed_tweets(author_id, processed_at desc);
create index if not exists idx_processed_ttl on public.processed_tweets(processed_at);

-- Table documentation
comment on table public.processed_tweets is 'Deduplication tracking for tweet processing (30d retention)';
comment on column public.processed_tweets.tweet_id is 'Twitter tweet ID (primary key)';
comment on column public.processed_tweets.author_id is 'Twitter user ID of tweet author';
comment on column public.processed_tweets.processed_at is 'When this tweet was processed';

-- ===============================================================
-- 2) FILTERING DECISIONS (audit trail with shadow testing)
-- ===============================================================

create table if not exists public.tweet_decisions (
  id             bigserial primary key,
  tweet_id       text not null,
  author_id      text not null,
  tweet_text     text,
  stage_quick    text not null,                      -- 'pass'|'reject'|'error'
  quick_reason   text,
  stage_ai       text not null,                      -- 'pass'|'reject'|'skipped'
  ai_score       numeric not null default 0,
  ai_reason      text,
  final          text not null,                      -- 'approved'|'rejected'
  categories     jsonb,                              -- AI categories array
  model_json     jsonb,                              -- Full AI response
  filter_version text not null default 'v2',         -- 'v1'|'v2'|'seed'
  processing_time_ms integer default 0,
  relevance_threshold numeric default 80.0,
  created_at     timestamptz not null default now()
);

-- Performance indexes
create index if not exists idx_decisions_tweet on public.tweet_decisions(tweet_id);
create index if not exists idx_decisions_final_time on public.tweet_decisions(final, created_at desc);
create index if not exists idx_decisions_author_time on public.tweet_decisions(author_id, created_at desc);
create index if not exists idx_decisions_version on public.tweet_decisions(filter_version, created_at desc);
create index if not exists idx_decisions_created_at on public.tweet_decisions(created_at desc);

-- Prevent duplicate decisions per tweet per version (shadow testing support)
create unique index if not exists uq_decision_version
on public.tweet_decisions(tweet_id, filter_version);

-- Table documentation
comment on table public.tweet_decisions is 'V2 filtering audit trail with AI scores, reasoning, and shadow testing support';
comment on column public.tweet_decisions.tweet_id is 'Twitter tweet ID';
comment on column public.tweet_decisions.author_id is 'Twitter user ID of tweet author';
comment on column public.tweet_decisions.tweet_text is 'Tweet content for reference';
comment on column public.tweet_decisions.stage_quick is 'Quick filter result: pass, reject, or error';
comment on column public.tweet_decisions.stage_ai is 'AI filter result: pass, reject, or skipped';
comment on column public.tweet_decisions.final is 'Final decision: approved or rejected';
comment on column public.tweet_decisions.filter_version is 'Filter version: v1, v2, or seed (for testing)';

-- ===============================================================
-- 3) RATE LIMITING TABLE
-- ===============================================================

create table if not exists public.manual_replies (
  id             bigserial primary key,
  tweet_id       text not null,
  author_id      text not null,
  action         text not null,                      -- 'reply'|'retweet'|'like'
  status         text not null default 'pending',    -- 'pending'|'sent'|'failed'
  acted_at       timestamptz not null default now(),
  meta           jsonb
);

-- Performance index for rate limiting queries
create index if not exists idx_manual_author_time on public.manual_replies(author_id, acted_at desc);
create index if not exists idx_manual_status_time on public.manual_replies(status, acted_at desc);

-- Table documentation
comment on table public.manual_replies is 'Manual action history for rate limiting and tracking';
comment on column public.manual_replies.action is 'Type of action: reply, retweet, or like';
comment on column public.manual_replies.status is 'Action status: pending, sent, or failed';

-- ===============================================================
-- 4) STABLE VIEWS FOR UI AND MONITORING
-- ===============================================================

-- Main UI view - only approved tweets
create or replace view public.v_approved_tweets as
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

comment on view public.v_approved_tweets is 'Stable interface for UI - only approved tweets sorted by decision time';

-- Shadow comparison view for V1 vs V2 performance
create or replace view public.v_filter_comparison as
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

comment on view public.v_filter_comparison is 'Compare V1 vs V2 filter performance over last 24 hours';

-- Health monitoring view
create or replace view public.v_filter_health as
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

comment on view public.v_filter_health is 'Hourly health metrics for filtering pipeline';

-- ===============================================================
-- 5) ROW LEVEL SECURITY (RLS) POLICIES
-- ===============================================================

-- Enable RLS
alter table public.processed_tweets enable row level security;
alter table public.tweet_decisions  enable row level security;
alter table public.manual_replies   enable row level security;

-- Service role policies (backend with service key)
create policy service_all_processed on public.processed_tweets
  for all to service_role using (true) with check (true);

create policy service_all_decisions on public.tweet_decisions
  for all to service_role using (true) with check (true);

create policy service_all_manual on public.manual_replies
  for all to service_role using (true) with check (true);

-- Anonymous role policies (browser UI)
create policy anon_read_approved on public.tweet_decisions
  for select to anon using (final = 'approved');

-- Allow read access to views for monitoring
grant select on public.v_approved_tweets to anon, authenticated;
grant select on public.v_filter_comparison to anon, authenticated;
grant select on public.v_filter_health to anon, authenticated;

-- ===============================================================
-- 6) STAGING SEED DATA FOR QA VERIFICATION
-- ===============================================================

-- Insert test data for one-click QA validation
insert into public.tweet_decisions (
  tweet_id, 
  author_id, 
  tweet_text,
  stage_quick, 
  stage_ai, 
  final, 
  ai_score, 
  ai_reason, 
  filter_version,
  categories
) values
-- REJECTED tweets (lifestyle/personal content) - should be 0% approval
('seed_reject_1', 'lifestyle_user1', 'Beautiful sunset at the lake tonight! 🌅', 'reject', 'skipped', 'rejected', 0, 'blacklist_keyword: sunset', 'seed', '[]'::jsonb),
('seed_reject_2', 'lifestyle_user2', 'Fire in the sky this summer at Lake George NY', 'reject', 'skipped', 'rejected', 0, 'blacklist_keyword: fire in the sky', 'seed', '[]'::jsonb),
('seed_reject_3', 'lifestyle_user3', 'Just finished my morning workout! Feeling great 💪', 'reject', 'skipped', 'rejected', 0, 'blacklist_keyword: workout', 'seed', '[]'::jsonb),
('seed_reject_4', 'lifestyle_user4', 'Family dinner tonight with the kids #blessed', 'reject', 'skipped', 'rejected', 0, 'blacklist_keyword: family dinner', 'seed', '[]'::jsonb),
('seed_reject_5', 'lifestyle_user5', 'RT Amazing weather today! Perfect for a beach day', 'reject', 'skipped', 'rejected', 0, 'retweet_no_tech', 'seed', '[]'::jsonb),

-- APPROVED tweets (technical content) - should have high approval rate
('seed_approve_1', 'tech_user1', 'New Python asyncio patterns for building scalable AI applications: 1) Task groups for parallel processing 2) Event loops with custom executors 3) Memory-efficient streaming. Implementation details at github.com/example/ai-patterns', 'pass', 'pass', 'approved', 85, 'Technical implementation with concrete details', 'seed', '["Programming", "DevTools"]'::jsonb),
('seed_approve_2', 'tech_user2', 'OpenAI function calling with structured outputs is a game changer for reliable AI agents. Here''s how to implement it with Pydantic schemas for type safety and validation in production systems.', 'pass', 'pass', 'approved', 82, 'AI/ML tutorial with implementation guidance', 'seed', '["AI News", "Programming"]'::jsonb),
('seed_approve_3', 'tech_user3', 'Tutorial: Building RAG systems with vector embeddings. Step 1: Document chunking (512 tokens) Step 2: Generate embeddings (text-embedding-3-large) Step 3: Vector DB (Pinecone/Weaviate) Step 4: Retrieval + LLM synthesis. Code: github.com/example/rag-tutorial', 'pass', 'pass', 'approved', 87, 'Comprehensive technical tutorial with implementation steps', 'seed', '["Programming", "DevTools", "AI News"]'::jsonb)

-- Handle conflicts gracefully (in case seed data already exists)
on conflict (tweet_id, filter_version) do nothing;

-- ===============================================================
-- 7) MAINTENANCE AND CLEANUP
-- ===============================================================

-- Function to clean up old processed tweets (30 day TTL)
create or replace function cleanup_processed_tweets()
returns void
language plpgsql
security definer
as $$
begin
  delete from public.processed_tweets 
  where processed_at < now() - interval '30 days';
end;
$$;

comment on function cleanup_processed_tweets() is 'Clean up processed tweets older than 30 days (run nightly)';

-- Function to get filter health stats
create or replace function get_filter_stats(hours_back integer default 24)
returns table(
  metric text,
  value numeric
)
language plpgsql
security definer
as $$
begin
  return query
  select 'total_processed'::text, count(*)::numeric from tweet_decisions where created_at > now() - (hours_back || ' hours')::interval and filter_version != 'seed'
  union all
  select 'approved'::text, count(*)::numeric from tweet_decisions where created_at > now() - (hours_back || ' hours')::interval and filter_version != 'seed' and final = 'approved'
  union all
  select 'approval_rate_percent'::text, 
    round(
      count(*) filter (where final = 'approved') * 100.0 / nullif(count(*), 0), 
      1
    )::numeric 
  from tweet_decisions 
  where created_at > now() - (hours_back || ' hours')::interval and filter_version != 'seed'
  union all
  select 'avg_processing_time_ms'::text, round(avg(processing_time_ms), 0)::numeric from tweet_decisions where created_at > now() - (hours_back || ' hours')::interval and filter_version != 'seed';
end;
$$;

comment on function get_filter_stats(integer) is 'Get key filtering metrics for monitoring dashboard';

-- ===============================================================
-- MIGRATION COMPLETE
-- ===============================================================

-- Log successful migration
insert into public.tweet_decisions (
  tweet_id, 
  author_id, 
  tweet_text,
  stage_quick, 
  stage_ai, 
  final, 
  ai_score, 
  ai_reason, 
  filter_version
) values (
  'migration_20250820', 
  'system', 
  'Database migration 20250820_filtering_v2 completed successfully',
  'pass', 
  'skipped', 
  'approved', 
  100, 
  'Migration completed - V2 filtering infrastructure ready', 
  'system'
) on conflict (tweet_id, filter_version) do nothing;

-- Verify tables exist with a simple health check
do $$
begin
  -- Test each table
  perform 1 from public.processed_tweets limit 1;
  perform 1 from public.tweet_decisions limit 1;
  perform 1 from public.manual_replies limit 1;
  
  -- Test views
  perform 1 from public.v_approved_tweets limit 1;
  perform 1 from public.v_filter_comparison limit 1;
  perform 1 from public.v_filter_health limit 1;
  
  raise notice 'Migration verification successful - all tables and views created';
end;
$$;