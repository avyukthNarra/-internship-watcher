-- Behaviour tests for the init migration. Every check raises on failure (run with ON_ERROR_STOP).
\set ON_ERROR_STOP on

-- Pipeline data (as the owner, like the service role).
insert into public.jobs (id, identity, company, title, url, source)
values ('greenhouse:acme:1', 'acme|swe intern', 'Acme', 'SWE Intern', 'https://example.com/1', 'greenhouse'),
       ('lever:beta:2', 'beta|ml intern', 'Beta', 'ML Intern', 'https://example.com/2', 'lever');
insert into public.default_top_companies values ('Acme'), ('Gamma');

-- Two sign-ups: A via Discord, B via Google.
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-00000000000a', 'a@example.com', '{"full_name": "User A"}'),
  ('00000000-0000-0000-0000-00000000000b', 'b@example.com', '{"name": "User B"}');
insert into auth.identities (user_id, provider, provider_id) values
  ('00000000-0000-0000-0000-00000000000a', 'discord', '111222333444555666'),
  ('00000000-0000-0000-0000-00000000000b', 'google', 'g-123');

do $$ begin
  assert (select count(*) from public.profiles) = 2, 'profiles created on sign-up';
  assert (select count(*) from public.user_preferences) = 2, 'preferences created on sign-up';
  assert (select discord_user_id from public.profiles where email = 'a@example.com') = '111222333444555666', 'discord id recorded';
  assert (select discord_user_id from public.profiles where email = 'b@example.com') is null, 'no discord id for google user';
end $$;

-- ---------------------------------------------------------------- act as user A
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false);

insert into public.user_jobs (user_id, job_id) values ('00000000-0000-0000-0000-00000000000a', 'greenhouse:acme:1');
update public.user_jobs set status = 'applied' where job_id = 'greenhouse:acme:1';
insert into public.user_top_company_overrides values
  ('00000000-0000-0000-0000-00000000000a', 'Gamma', 'remove'),
  ('00000000-0000-0000-0000-00000000000a', 'Beta', 'add');
update public.user_preferences set roles = '{ML}' where user_id = '00000000-0000-0000-0000-00000000000a';

do $$ begin
  assert (select applied_at is not null from public.user_jobs where job_id = 'greenhouse:acme:1'), 'applied_at stamped';
  assert (select follow_up_on = (applied_at + interval '14 days')::date from public.user_jobs
           where job_id = 'greenhouse:acme:1'), 'follow-up defaulted to 14 days';
  assert (select count(*) from public.user_job_events) = 2, 'saved + applied events logged';
  assert (select array_agg(company order by company) from public.user_top_companies) = '{Acme,Beta}',
         'top list = default + add - remove';
  assert (select count(*) from public.profiles) = 1, 'A sees only own profile';
  assert (select count(*) from public.jobs) = 2, 'jobs readable';
end $$;

-- A cannot write rows for B, set its own Discord ID, or touch pipeline tables.
do $$ begin
  begin
    insert into public.user_jobs (user_id, job_id) values ('00000000-0000-0000-0000-00000000000b', 'lever:beta:2');
    raise exception 'FAIL: wrote a row for another user';
  exception when insufficient_privilege then null; end;
  begin
    update public.profiles set discord_user_id = '999' where user_id = '00000000-0000-0000-0000-00000000000a';
    raise exception 'FAIL: changed own discord id';
  exception when insufficient_privilege then null; end;
  begin
    perform 1 from public.state_docs;
    raise exception 'FAIL: read pipeline state';
  exception when insufficient_privilege then null; end;
  begin
    insert into public.jobs (id, identity, company, title, url, source) values ('x', 'x', 'x', 'x', 'x', 'x');
    raise exception 'FAIL: user inserted a job';
  exception when insufficient_privilege then null; end;
end $$;

-- ---------------------------------------------------------------- act as user B
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false);
do $$ begin
  assert (select count(*) from public.user_jobs) = 0, 'B cannot see A''s tracker';
  assert (select count(*) from public.user_job_events) = 0, 'B cannot see A''s history';
  assert (select array_agg(company order by company) from public.user_top_companies) = '{Acme,Gamma}',
         'B gets the plain default list';
end $$;
update public.user_jobs set status = 'offer';   -- touches nothing: RLS hides A's rows

-- ---------------------------------------------------------------- anonymous visitor
set role anon;
select set_config('request.jwt.claim.sub', '', false);
do $$ begin
  assert (select count(*) from public.jobs) = 2, 'anon can read jobs';
  begin
    perform 1 from public.user_jobs;
    raise exception 'FAIL: anon read trackers';
  exception when insufficient_privilege then null; end;
end $$;
reset role;

do $$ begin
  assert (select status from public.user_jobs where job_id = 'greenhouse:acme:1') = 'applied', 'B could not modify A''s row';
end $$;

-- Deleting an account cascades through all of its data.
delete from auth.users where id = '00000000-0000-0000-0000-00000000000a';
do $$ begin
  assert (select count(*) from public.user_jobs) = 0, 'tracker deleted with account';
  assert (select count(*) from public.user_top_company_overrides) = 0, 'overrides deleted with account';
  assert (select count(*) from public.user_job_events) = 0, 'history deleted with account';
end $$;

select 'ALL RLS TESTS PASSED' as result;
