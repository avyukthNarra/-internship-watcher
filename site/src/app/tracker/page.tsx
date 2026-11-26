import { createClient } from "@/lib/supabase/server";
import { TrackerTable, type TrackerRow } from "@/components/tracker-table";
import type { ApplicationStatus } from "@/lib/database.types";

export default async function Tracker() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  const { data: rawTracked } = await supabase.from("user_jobs").select("job_id,status,saved_at,applied_at,follow_up_on,notes").eq("user_id", user.id).order("updated_at", { ascending: false }).range(0, 99);
  const tracked = (rawTracked ?? []) as unknown as { job_id: string; status: ApplicationStatus; saved_at: string; applied_at: string | null; follow_up_on: string | null; notes: string | null }[];
  const ids = tracked.map((row) => row.job_id);
  let jobs: { id: string; company: string; title: string; url: string }[] = [];
  let events: { job_id: string; status: ApplicationStatus; at: string }[] = [];
  if (ids.length) {
    const [jobResult, eventResult] = await Promise.all([
      supabase.from("jobs").select("id,company,title,url").in("id", ids),
      supabase.from("user_job_events").select("job_id,status,at").eq("user_id", user.id).in("job_id", ids).order("at", { ascending: false }).limit(500),
    ]);
    jobs = (jobResult.data ?? []) as unknown as typeof jobs;
    events = (eventResult.data ?? []) as unknown as typeof events;
  }
  const jobById = new Map(jobs.map((job) => [job.id, job]));
  const eventsById = new Map<string, TrackerRow["events"]>();
  for (const event of events) eventsById.set(event.job_id, [...(eventsById.get(event.job_id) ?? []), { status: event.status, at: event.at }]);
  const rows: TrackerRow[] = tracked.flatMap((row) => {
    const job = jobById.get(row.job_id);
    return job ? [{ jobId: row.job_id, company: job.company, title: job.title, url: job.url, status: row.status, appliedAt: row.applied_at, followUpOn: row.follow_up_on, notes: row.notes, savedAt: row.saved_at, events: eventsById.get(row.job_id) ?? [] }] : [];
  });
  return <><section className="page-heading"><div className="eyebrow">Your search, organized</div><h1>Application tracker</h1><p>Every role you save, with the next step close at hand.</p></section><TrackerTable initialRows={rows} userId={user.id} /></>;
}
