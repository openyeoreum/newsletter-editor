create extension if not exists pgcrypto;

create table if not exists public.drafts (
  id text primary key,
  name text not null,
  template text not null default 'classic',
  subject text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.app_settings (
  key text primary key,
  value jsonb
);

create table if not exists public.subscribers (
  email text primary key,
  name text not null default '',
  organization text not null default '',
  subscribed_at timestamptz not null default now(),
  consent_source text not null default 'public_subscribe_form',
  consent_version text not null default '',
  ip text not null default '',
  user_agent text not null default ''
);

alter table public.subscribers
  add column if not exists organization text not null default '',
  add column if not exists subscribed_at timestamptz not null default now(),
  add column if not exists consent_source text not null default 'public_subscribe_form',
  add column if not exists consent_version text not null default '',
  add column if not exists ip text not null default '',
  add column if not exists user_agent text not null default '';

create table if not exists public.unsubscribed (
  email text primary key,
  unsubscribed_at timestamptz not null default now()
);

create table if not exists public.send_jobs (
  id text primary key,
  sender text not null,
  template text not null,
  subject text not null,
  from_addr text not null default '',
  from_name text not null default '전인교육학회',
  data jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  total integer not null default 0,
  sent integer not null default 0,
  failed integer not null default 0,
  skipped integer not null default 0,
  current_chunk integer not null default 0,
  total_chunks integer not null default 0,
  errors jsonb not null default '[]'::jsonb,
  message text not null default '',
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table if not exists public.send_job_recipients (
  id uuid primary key default gen_random_uuid(),
  job_id text not null references public.send_jobs(id) on delete cascade,
  email text not null,
  name text,
  status text not null default 'pending',
  error text,
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  unique(job_id, email)
);

create index if not exists send_job_recipients_job_status_idx
  on public.send_job_recipients(job_id, status, created_at);

alter table public.drafts enable row level security;
alter table public.app_settings enable row level security;
alter table public.subscribers enable row level security;
alter table public.unsubscribed enable row level security;
alter table public.send_jobs enable row level security;
alter table public.send_job_recipients enable row level security;
