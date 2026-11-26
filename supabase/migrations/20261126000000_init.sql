-- Internship watcher: jobs, user accounts, per-user tracker and top-company lists.
-- See dbplan.md. Applied with scripts/db_apply.sh (psql, single transaction).

-- ---------------------------------------------------------------- jobs (pipeline writes, everyone reads)
create table public.jobs (
  id          text primary key,                 -- watcher id, e.g. 'greenhouse:anthropic:123'
  identity    text not null,                    -- job_utils.job_identity, cross-source dedupe
  company     text not null,
  title       text not null,
  location    text not null default '',
  url         text not null,
  terms       text[] not null default '{}',
  source      text not null,
  category    text,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  closed_at   timestamptz
);
create index jobs_first_seen_idx on public.jobs (first_seen desc);
create index jobs_identity_idx on public.jobs (identity);
create index jobs_company_idx on public.jobs (lower(company));

create table public.default_top_companies (
  name text primary key                         -- synced from config.json each pipeline run
);

-- ---------------------------------------------------------------- accounts
create table public.profiles (
  user_id          uuid primary key references auth.users (id) on delete cascade,
  display_name     text,
  discord_user_id  text unique,                 -- set from the Discord identity, never by the user
  email            text,
  notify_dm        boolean not null default false,
  notify_email     boolean not null default false,
  created_at       timestamptz not null default now()
);

create table public.user_preferences (          -- fields job_utils.preference_matches understands
  user_id            uuid primary key references public.profiles (user_id) on delete cascade,
  roles              text[] not null default '{}',
  locations          text[] not null default '{}',
  terms              text[] not null default '{}',
  exclude_roles      text[] not null default '{}',
  categories         text[] not null default '{}',
  keep_unknown_terms boolean not null default true,
  only_top_companies boolean not null default true,
  follow_up_days     int not null default 14 check (follow_up_days between 0 and 365),
  updated_at         timestamptz not null default now()
);

-- Each user's top list = repo default + their adds - their removes, so repo additions still reach them.
create table public.user_top_company_overrides (
  user_id  uuid not null references public.profiles (user_id) on delete cascade,
  company  text not null check (length(company) between 1 and 200),
  action   text not null check (action in ('add', 'remove')),
  primary key (user_id, company)
);

create view public.user_top_companies with (security_invoker = true) as
  select p.user_id, d.name as company
    from public.profiles p
    cross join public.default_top_companies d
   where not exists (select 1 from public.user_top_company_overrides o
                      where o.user_id = p.user_id and o.company = d.name and o.action = 'remove')
  union
  select o.user_id, o.company
    from public.user_top_company_overrides o
   where o.action = 'add';

-- ---------------------------------------------------------------- per-user tracker
create type public.application_status as enum
  ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn');

create table public.user_jobs (
  user_id       uuid not null references public.profiles (user_id) on delete cascade,
  job_id        text not null references public.jobs (id) on delete restrict,
  status        public.application_status not null default 'saved',
  saved_at      timestamptz not null default now(),
  applied_at    timestamptz,
  follow_up_on  date,
  notes         text check (length(notes) <= 5000),
  source        text not null default 'web' check (source in ('web', 'discord_pin', 'discord_applied', 'import')),
  updated_at    timestamptz not null default now(),
  primary key (user_id, job_id)
);
create index user_jobs_user_status_idx on public.user_jobs (user_id, status);

create table public.user_job_events (           -- history of every status change
  id       bigint generated always as identity primary key,
  user_id  uuid not null references public.profiles (user_id) on delete cascade,
  job_id   text not null,
  status   public.application_status not null,
  at       timestamptz not null default now()
);
create index user_job_events_user_idx on public.user_job_events (user_id, at desc);

-- ---------------------------------------------------------------- pipeline-only tables
create table public.notifications (             -- per-user alert ledger: dedupe + retries
  user_id   uuid not null references public.profiles (user_id) on delete cascade,
  job_id    text not null references public.jobs (id) on delete cascade,
  channel   text not null check (channel in ('dm', 'email')),
  status    text not null default 'pending' check (status in ('pending', 'sent', 'dead')),
  attempts  int not null default 0,
  error     text,
  created_at timestamptz not null default now(),
  sent_at   timestamptz,
  primary key (user_id, job_id, channel)
);
create index notifications_pending_idx on public.notifications (status) where status = 'pending';

create table public.state_docs (                -- watcher internal state as JSON documents (state_db.py)
  name       text primary key,
  kind       text not null check (kind in ('dict', 'value')),
  value      jsonb,
  updated_at timestamptz not null default now()
);
create table public.state_parts (
  name       text not null references public.state_docs (name) on delete cascade,
  key        text not null,
  value      jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (name, key)
);

-- ---------------------------------------------------------------- triggers
-- New sign-up: create profile + default preferences.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (user_id, display_name, email)
  values (new.id,
          coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
          new.email);
  insert into public.user_preferences (user_id) values (new.id);
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Discord identity (first login or linked later): record the Discord user ID.
create function public.handle_new_identity() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.provider = 'discord' then
    update public.profiles set discord_user_id = new.provider_id where user_id = new.user_id;
  end if;
  return new;
end $$;
create trigger on_auth_identity_created after insert on auth.identities
  for each row execute function public.handle_new_identity();

-- Tracker: stamp applied_at the first time a job becomes 'applied', default the follow-up, log history.
create function public.user_jobs_before_write() returns trigger
language plpgsql security definer set search_path = '' as $$
declare days int;
begin
  new.updated_at := now();
  if new.status <> 'saved' and new.applied_at is null then
    new.applied_at := now();
  end if;
  if new.applied_at is not null and new.follow_up_on is null then
    select follow_up_days into days from public.user_preferences where user_id = new.user_id;
    if coalesce(days, 14) > 0 then
      new.follow_up_on := (new.applied_at + make_interval(days => coalesce(days, 14)))::date;
    end if;
  end if;
  return new;
end $$;
create trigger user_jobs_before_write before insert or update on public.user_jobs
  for each row execute function public.user_jobs_before_write();

create function public.user_jobs_log_event() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.status is distinct from old.status then
    insert into public.user_job_events (user_id, job_id, status) values (new.user_id, new.job_id, new.status);
  end if;
  return null;
end $$;
create trigger user_jobs_log_event after insert or update on public.user_jobs
  for each row execute function public.user_jobs_log_event();

create function public.touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin new.updated_at := now(); return new; end $$;
create trigger user_preferences_touch before update on public.user_preferences
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------- row-level security
alter table public.jobs                       enable row level security;
alter table public.default_top_companies      enable row level security;
alter table public.profiles                   enable row level security;
alter table public.user_preferences           enable row level security;
alter table public.user_top_company_overrides enable row level security;
alter table public.user_jobs                  enable row level security;
alter table public.user_job_events            enable row level security;
alter table public.notifications              enable row level security;   -- no policies: pipeline only
alter table public.state_docs                 enable row level security;   -- no policies: pipeline only
alter table public.state_parts                enable row level security;   -- no policies: pipeline only

create policy "jobs are public" on public.jobs
  for select to anon, authenticated using (true);
create policy "default top companies are public" on public.default_top_companies
  for select to anon, authenticated using (true);

create policy "read own profile" on public.profiles
  for select to authenticated using (user_id = (select auth.uid()));
create policy "update own profile" on public.profiles
  for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "read own preferences" on public.user_preferences
  for select to authenticated using (user_id = (select auth.uid()));
create policy "update own preferences" on public.user_preferences
  for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "manage own top list" on public.user_top_company_overrides
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "manage own tracker" on public.user_jobs
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "read own history" on public.user_job_events
  for select to authenticated using (user_id = (select auth.uid()));

-- Column-level limits: users may not set their own Discord ID, email, or identity fields.
revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (display_name, notify_dm, notify_email) on public.profiles to authenticated;

revoke all on public.user_preferences from anon, authenticated;
grant select on public.user_preferences to authenticated;
grant update (roles, locations, terms, exclude_roles, categories, keep_unknown_terms,
              only_top_companies, follow_up_days) on public.user_preferences to authenticated;

revoke all on public.user_job_events from anon, authenticated;
grant select on public.user_job_events to authenticated;

revoke all on public.jobs, public.default_top_companies from anon, authenticated;
grant select on public.jobs, public.default_top_companies to anon, authenticated;

revoke all on public.notifications, public.state_docs, public.state_parts from anon, authenticated;

grant select, insert, update, delete on public.user_top_company_overrides, public.user_jobs to authenticated;
revoke all on public.user_top_company_overrides, public.user_jobs from anon;
grant select on public.user_top_companies to authenticated;
revoke all on public.user_top_companies from anon;

revoke execute on function public.handle_new_user(), public.handle_new_identity(),
  public.user_jobs_before_write(), public.user_jobs_log_event() from public, anon, authenticated;
