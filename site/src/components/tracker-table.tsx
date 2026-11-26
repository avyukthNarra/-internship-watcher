"use client";

import { useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { dateLabel, statuses } from "@/lib/utils";
import type { ApplicationStatus } from "@/lib/database.types";

export type TrackerRow = { jobId: string; company: string; title: string; url: string; status: ApplicationStatus; appliedAt: string | null; followUpOn: string | null; notes: string | null; savedAt: string; events: { status: ApplicationStatus; at: string }[] };

export function TrackerTable({ initialRows, userId }: { initialRows: TrackerRow[]; userId: string }) {
  const [rows, setRows] = useState(initialRows);
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<keyof TrackerRow>("savedAt");
  const [ascending, setAscending] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const visible = useMemo(() => rows.filter((row) => filter === "all" || row.status === filter).sort((a, b) => {
    const av = String(a[sort] ?? ""); const bv = String(b[sort] ?? "");
    return av.localeCompare(bv) * (ascending ? 1 : -1);
  }), [rows, filter, sort, ascending]);
  async function update(jobId: string, values: { status?: ApplicationStatus; notes?: string }) {
    const { error } = await createClient().from("user_jobs").update(values).eq("user_id", userId).eq("job_id", jobId);
    setMessage(error ? "Could not save this update." : "Changes saved.");
    if (!error) setRows((current) => current.map((row) => row.jobId === jobId ? { ...row, ...values } : row));
  }
  function exportCsv() {
    const fields = ["company", "title", "status", "appliedAt", "followUpOn", "notes", "url"] as const;
    const csv = [fields.join(","), ...visible.map((row) => fields.map((key) => `"${String(row[key] ?? "").replaceAll('"', '""')}"`).join(","))].join("\r\n");
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); link.download = "internship-tracker.csv"; link.click(); URL.revokeObjectURL(link.href);
  }
  function sortBy(key: keyof TrackerRow) { if (key === sort) setAscending(!ascending); else { setSort(key); setAscending(true); } }
  return <><div className="table-toolbar"><div className="toolbar-group"><select className="control" aria-label="Filter by status" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All statuses</option>{statuses.map((status) => <option value={status} key={status}>{status}</option>)}</select><span className="muted">{visible.length} tracked</span></div><button className="secondary-button" onClick={exportCsv}>Export CSV ↓</button></div>{message && <p className="muted" role="status">{message}</p>}<div className="table-wrap"><table><thead><tr>{[["company", "Company"], ["title", "Role"], ["status", "Status"], ["appliedAt", "Applied"], ["followUpOn", "Follow up"], ["notes", "Notes"]].map(([key, label]) => <th key={key}><button className="history-button" onClick={() => sortBy(key as keyof TrackerRow)}>{label} {sort === key ? ascending ? "↑" : "↓" : "↕"}</button></th>)}<th>History</th></tr></thead><tbody>{visible.map((row) => <tr key={row.jobId}><td>{row.company}</td><td><a className="apply-link" href={row.url} target="_blank" rel="noopener noreferrer">{row.title} ↗</a></td><td><select className="table-select" aria-label={`Status for ${row.title}`} value={row.status} onChange={(e) => update(row.jobId, { status: e.target.value as ApplicationStatus })}>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></td><td>{dateLabel(row.appliedAt)}</td><td>{dateLabel(row.followUpOn)}</td><td><input className="table-input" aria-label={`Notes for ${row.title}`} defaultValue={row.notes ?? ""} maxLength={5000} onBlur={(e) => { if (e.currentTarget.value !== (row.notes ?? "")) update(row.jobId, { notes: e.currentTarget.value }); }} placeholder="Add a note…" /></td><td><button className="history-button" onClick={() => setOpen(open === row.jobId ? null : row.jobId)}>{open === row.jobId ? "Hide" : `${row.events.length} events`}</button>{open === row.jobId && <div className="history-list">{row.events.length ? row.events.map((event, index) => <div key={`${event.at}-${index}`}>{event.status} · {dateLabel(event.at)}</div>) : "No status changes yet."}</div>}</td></tr>)}</tbody></table>{visible.length === 0 && <div className="empty-state">Nothing here yet. Save a role from Explore to start tracking it.</div>}</div></>;
}
