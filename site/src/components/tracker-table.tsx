"use client";

import { useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { dateLabel, statuses } from "@/lib/utils";
import type { ApplicationStatus } from "@/lib/database.types";

export type TrackerRow = { jobId: string; company: string; title: string; url: string; status: ApplicationStatus; appliedAt: string | null; followUpOn: string | null; notes: string | null; savedAt: string; events: { status: ApplicationStatus; at: string }[] };

export function TrackerTable({ initialRows, userId, hasMore: initialHasMore, initialError }: { initialRows: TrackerRow[]; userId: string; hasMore: boolean; initialError: string }) {
  const [rows, setRows] = useState(initialRows);
  const [hasMore, setHasMore] = useState(initialHasMore && !initialError);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<keyof TrackerRow>("savedAt");
  const [ascending, setAscending] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [message, setMessage] = useState(initialError ? `Could not load tracker: ${initialError}` : "");
  const [loadingMore, setLoadingMore] = useState(false);
  const visible = useMemo(() => rows.filter((row) => filter === "all" || row.status === filter).sort((a, b) => {
    const av = String(a[sort] ?? ""); const bv = String(b[sort] ?? "");
    return av.localeCompare(bv) * (ascending ? 1 : -1);
  }), [rows, filter, sort, ascending]);
  async function update(jobId: string, values: { status?: ApplicationStatus; notes?: string }) {
    setMessage("");
    const supabase = createClient();
    const result = await supabase.from("user_jobs").update(values).eq("user_id", userId).eq("job_id", jobId).select("status,applied_at,follow_up_on,notes").maybeSingle();
    if (result.error) { setMessage(`Could not save this update: ${result.error.message}`); return; }
    if (!result.data) { setMessage("No tracker row was updated. Refresh and try again."); return; }
    const updated = result.data;
    let events: TrackerRow["events"] | undefined;
    if (values.status) {
      const history = await supabase.from("user_job_events").select("status,at").eq("user_id", userId).eq("job_id", jobId).order("at", { ascending: false }).limit(100);
      if (history.error) setMessage(`Status was saved, but history could not be refreshed: ${history.error.message}`);
      else events = history.data ?? [];
    } else setMessage("Changes saved.");
    setRows((current) => current.map((row) => row.jobId === jobId ? { ...row, status: updated.status, appliedAt: updated.applied_at, followUpOn: updated.follow_up_on, notes: updated.notes, ...(events ? { events } : {}) } : row));
  }
  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true); setMessage("");
    const supabase = createClient();
    const { data: tracked, error: trackedError, count } = await supabase.from("user_jobs").select("job_id,status,saved_at,applied_at,follow_up_on,notes", { count: "exact" }).eq("user_id", userId).order("updated_at", { ascending: false }).range(rows.length, rows.length + 99);
    if (trackedError) { setMessage(`Could not load more tracker rows: ${trackedError.message}`); setLoadingMore(false); return; }
    const ids = tracked.map((row) => row.job_id);
    if (ids.length) {
      const [jobResult, eventResult] = await Promise.all([
        supabase.from("jobs").select("id,company,title,url").in("id", ids),
        supabase.from("user_job_events").select("job_id,status,at").eq("user_id", userId).in("job_id", ids).order("at", { ascending: false }).limit(500),
      ]);
      if (jobResult.error || eventResult.error) {
        setMessage(`Could not load more tracker details: ${jobResult.error?.message ?? eventResult.error?.message}`);
        setLoadingMore(false); return;
      }
      const jobById = new Map((jobResult.data ?? []).map((job) => [job.id, job]));
      const eventsById = new Map<string, TrackerRow["events"]>();
      for (const event of eventResult.data ?? []) eventsById.set(event.job_id, [...(eventsById.get(event.job_id) ?? []), { status: event.status, at: event.at }]);
      const added = tracked.flatMap((row) => {
        const job = jobById.get(row.job_id);
        return job ? [{ jobId: row.job_id, company: job.company, title: job.title, url: job.url, status: row.status, appliedAt: row.applied_at, followUpOn: row.follow_up_on, notes: row.notes, savedAt: row.saved_at, events: eventsById.get(row.job_id) ?? [] }] : [];
      });
      setRows((current) => [...current, ...added]);
    }
    setHasMore((count ?? 0) > rows.length + tracked.length);
    setLoadingMore(false);
  }
  function exportCsv() {
    const fields = ["company", "title", "status", "appliedAt", "followUpOn", "notes", "url"] as const;
    function csvCell(value: string | null) {
      let cell = value ?? "";
      if (/^\s*[=+\-@]/.test(cell)) cell = `'${cell}`;
      return `"${cell.replaceAll('"', '""')}"`;
    }
    const csv = [fields.join(","), ...visible.map((row) => fields.map((key) => csvCell(String(row[key] ?? ""))).join(","))].join("\r\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = "internship-tracker.csv"; link.click(); URL.revokeObjectURL(link.href);
  }
  function sortBy(key: keyof TrackerRow) { if (key === sort) setAscending(!ascending); else { setSort(key); setAscending(true); } }
  return <><div className="table-toolbar"><div className="toolbar-group"><select className="control" aria-label="Filter by status" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All statuses</option>{statuses.map((status) => <option value={status} key={status}>{status}</option>)}</select><span className="muted">{visible.length} shown · {rows.length}{hasMore ? "+" : ""} total</span></div><button className="secondary-button" onClick={exportCsv}>Export CSV ↓</button></div>{message && <p className={initialError ? "error-text" : "muted"} role={initialError ? "alert" : "status"}>{message}</p>}<div className="table-wrap"><table><thead><tr>{[["company", "Company"], ["title", "Role"], ["status", "Status"], ["appliedAt", "Applied"], ["followUpOn", "Follow up"], ["notes", "Notes"]].map(([key, label]) => <th key={key}><button className="history-button" onClick={() => sortBy(key as keyof TrackerRow)}>{label} {sort === key ? ascending ? "↑" : "↓" : "↕"}</button></th>)}<th>History</th></tr></thead><tbody>{visible.map((row) => <tr key={row.jobId}><td>{row.company}</td><td><a className="apply-link" href={row.url} target="_blank" rel="noopener noreferrer">{row.title} ↗</a></td><td><select className="table-select" aria-label={`Status for ${row.title}`} value={row.status} onChange={(e) => update(row.jobId, { status: e.target.value as ApplicationStatus })}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></td><td>{dateLabel(row.appliedAt)}</td><td>{dateLabel(row.followUpOn)}</td><td><input className="table-input" aria-label={`Notes for ${row.title}`} defaultValue={row.notes ?? ""} maxLength={5000} onBlur={(e) => { if (e.currentTarget.value !== (row.notes ?? "")) update(row.jobId, { notes: e.currentTarget.value }); }} placeholder="Add a note…" /></td><td><button className="history-button" onClick={() => setOpen(open === row.jobId ? null : row.jobId)}>{open === row.jobId ? "Hide" : `${row.events.length} events`}</button>{open === row.jobId && <div className="history-list">{row.events.length ? row.events.map((event, index) => <div key={`${event.at}-${index}`}>{event.status} · {dateLabel(event.at)}</div>) : "No status changes yet."}</div>}</td></tr>)}</tbody></table>{!visible.length && !initialError && <div className="empty-state">Nothing here yet. Save a role from Explore to start tracking it.</div>}</div>{hasMore && <div className="pagination"><button className="ghost-button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Loading…" : "Load more"}</button></div>}</>;
}
