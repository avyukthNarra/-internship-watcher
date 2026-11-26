"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export function JobActions({ jobId, userId, initialStatus }: { jobId: string; userId: string | null; initialStatus?: string }) {
  const [status, setStatus] = useState(initialStatus ?? "");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function save(next: "saved" | "applied") {
    if (!userId) { router.push(`/login?next=${encodeURIComponent("/")}`); return; }
    setBusy(true);
    const supabase = createClient();
    const { error } = await supabase.from("user_jobs").upsert({ user_id: userId, job_id: jobId, status: next }, { onConflict: "user_id,job_id" });
    setBusy(false);
    if (!error) { setStatus(next); router.refresh(); }
  }
  return <div className="job-actions"><button className={`small-action ${status === "saved" ? "applied" : ""}`} disabled={busy} onClick={() => save("saved")} aria-label="Save job">{status === "saved" ? "Saved ✓" : "☆ Save"}</button><button className={`small-action ${status === "applied" ? "applied" : ""}`} disabled={busy} onClick={() => save("applied")}>{status === "applied" ? "Applied ✓" : "Applied"}</button></div>;
}
