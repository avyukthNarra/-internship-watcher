import { createClient } from "@/lib/supabase/server";
import { TrackerTable, type TrackerRow } from "@/components/tracker-table";

export default async function Tracker() {
  const supabase = await createClient();
  const { data: { user }, error: authError } = await supabase.auth.getUser();
  if (!user) return null;
  const { data: tracked, count, error: trackerError } = await supabase.from("user_jobs")
    .select("job_id,status,saved_at,applied_at,follow_up_on,notes", { count: "exact" })
    .eq("user_id", user.id).order("updated_at", { ascending: false }).range(0, 99);
  let error = authError?.message ?? trackerError?.message ?? "";
  let rows: TrackerRow[] = [];
  const ids = (tracked ?? []).map((row) => row.job_id);
  if (!error && ids.length) {
    const [jobResult, eventResult] = await Promise.all([
      supabase.from("jobs").select("id,company,title,url").in("id", ids),
      supabase.from("user_job_events").select("job_id,status,at").eq("user_id", user.id).in("job_id", ids).order("at", { ascending: false }).limit(500),
    ]);
    error = jobResult.error?.message ?? eventResult.error?.message ?? "";
    if (!error) {
      const jobById = new Map((jobResult.data ?? []).map((job) => [job.id, job]));
      const eventsById = new Map<string, TrackerRow["events"]>();
      for (const event of eventResult.data ?? []) eventsById.set(event.job_id, [...(eventsById.get(event.job_id) ?? []), { status: event.status, at: event.at }]);
      rows = (tracked ?? []).flatMap((row) => {
        const job = jobById.get(row.job_id);
        return job ? [{ jobId: row.job_id, company: job.company, title: job.title, url: job.url, status: row.status, appliedAt: row.applied_at, followUpOn: row.follow_up_on, notes: row.notes, savedAt: row.saved_at, events: eventsById.get(row.job_id) ?? [] }] : [];
      });
    }
  }
  return <><section className="page-heading"><div className="eyebrow">Your search, organized</div><h1>Application tracker</h1><p>Every role you save, with the next step close at hand.</p></section><TrackerTable initialRows={rows} userId={user.id} hasMore={(count ?? 0) > (tracked?.length ?? 0)} initialError={error}/></>;
}
