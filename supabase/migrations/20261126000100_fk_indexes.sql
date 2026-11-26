-- Cover the job_id foreign keys flagged by the Supabase performance advisor
-- (deleting or closing a job looks up referencing rows by job_id).
create index user_jobs_job_id_idx on public.user_jobs (job_id);
create index notifications_job_id_idx on public.notifications (job_id);
