import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { PAGE_SIZE, queryText } from "@/lib/utils";
import { JobActions } from "@/components/job-actions";
import type { ApplicationStatus } from "@/lib/database.types";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
const sources = ["greenhouse", "lever", "ashby", "workday", "simplify", "vanshb03", "jobright"];
type FeedJob = { id: string; company: string; title: string; location: string; url: string; terms: string[]; source: string; category: string | null; first_seen: string };

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = queryText(params.q).trim();
  const term = queryText(params.term).trim();
  const location = queryText(params.location).trim();
  const source = queryText(params.source).trim();
  const topOnly = queryText(params.top) === "1";
  const page = Math.max(1, Number.parseInt(queryText(params.page) || "1", 10) || 1);
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const since = new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString();
  let companies: string[] = [];
  if (topOnly) {
    if (user) {
      const { data } = await supabase.from("user_top_companies").select("company").eq("user_id", user.id);
      companies = ((data ?? []) as unknown as { company: string }[]).map((row) => row.company);
    } else {
      const { data } = await supabase.from("default_top_companies").select("name");
      companies = ((data ?? []) as unknown as { name: string }[]).map((row) => row.name);
    }
  }
  let request = supabase.from("jobs").select("id,company,title,location,url,terms,source,category,first_seen", { count: "exact" })
    .gte("first_seen", since).order("first_seen", { ascending: false }).order("id", { ascending: true })
    .range((page - 1) * PAGE_SIZE, page * PAGE_SIZE - 1);
  if (query) request = request.or(`company.ilike.%${query}%,title.ilike.%${query}%,location.ilike.%${query}%`);
  if (term) request = request.contains("terms", [term]);
  if (location) request = request.ilike("location", `%${location}%`);
  if (source) request = request.eq("source", source);
  if (topOnly) request = companies.length ? request.in("company", companies) : request.eq("company", "__no_company_matches__");
  const result = await request;
  const jobs = (result.data ?? []) as unknown as FeedJob[];
  const count = result.count;
  let savedRows: { job_id: string; status: ApplicationStatus }[] = [];
  if (user) {
    const { data } = await supabase.from("user_jobs").select("job_id,status").eq("user_id", user.id).limit(1000);
    savedRows = ((data ?? []) as unknown as { job_id: string; status: ApplicationStatus }[]).map((row) => ({ job_id: row.job_id, status: row.status }));
  }
  const statuses = new Map(savedRows.map((row) => [row.job_id, row.status]));
  const pages = Math.max(1, Math.ceil((count ?? 0) / PAGE_SIZE));
  function pageHref(number: number) {
    const next = new URLSearchParams();
    for (const [key, value] of [["q", query], ["term", term], ["location", location], ["source", source]] as const) if (value) next.set(key, value);
    if (topOnly) next.set("top", "1");
    next.set("page", String(number));
    return `/?${next.toString()}`;
  }
  return <>
    <section className="hero"><div><div className="eyebrow">A better start, starts here</div><h1>Find your next<br/>internship.</h1><p>Fresh opportunities for the next generation of builders.</p></div><div className="hero-aside"><strong>{count ?? 0}</strong> roles in the last 45 days</div></section>
    <form className="filters" action="/" method="get">
      <label className="search-wrap"><span className="search-icon" aria-hidden="true">⌕</span><input className="control" type="search" name="q" defaultValue={query} placeholder="Search roles or companies" aria-label="Search roles or companies" /></label>
      <input className="control" name="term" defaultValue={term} placeholder="Term · e.g. Summer 2027" aria-label="Filter by term" />
      <input className="control" name="location" defaultValue={location} placeholder="Location" aria-label="Filter by location" />
      <select className="control" name="source" defaultValue={source} aria-label="Filter by source"><option value="">All sources</option>{sources.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}</select>
      {topOnly && <input type="hidden" name="top" value="1" />}<button className="filter-button" type="submit">Search <span aria-hidden="true">↗</span></button>
    </form>
    <div className="feed-toolbar"><span>Showing {count ? (page - 1) * PAGE_SIZE + 1 : 0}–{Math.min(page * PAGE_SIZE, count ?? 0)} of {count ?? 0} roles</span><form action="/" method="get" className="toggle-row">{query && <input type="hidden" name="q" value={query}/ >}{term && <input type="hidden" name="term" value={term}/ >}{location && <input type="hidden" name="location" value={location}/ >}{source && <input type="hidden" name="source" value={source}/ >}<input id="top" type="checkbox" name="top" value="1" defaultChecked={topOnly} onChange={(e) => e.currentTarget.form?.requestSubmit()} /><label htmlFor="top">Top companies only</label></form></div>
    <section className="job-grid" aria-label="Internship listings">{jobs?.length ? jobs.map((job) => {
      const isNew = Date.now() - new Date(job.first_seen).getTime() < 24 * 60 * 60 * 1000;
      const initials = job.company.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
      return <article className="job-card" key={job.id}><div className="company-line"><span className="company-logo">{initials}</span><div style={{ minWidth: 0 }}><div className="company-name">{job.company}</div><div className="company-meta">{job.source}</div></div></div><h2 className="job-title">{job.title}</h2><div className="job-location"><span aria-hidden="true">⌖</span>{job.location || "Location not listed"}</div><div className="job-chips">{job.terms.slice(0, 3).map((item) => <span className="chip" key={item}>{item}</span>)}{isNew && <span className="chip fresh">New today</span>}</div><div className="job-bottom"><span className="seen">{new Date(job.first_seen).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span><div className="job-actions"><JobActions jobId={job.id} userId={user?.id ?? null} initialStatus={statuses.get(job.id)} /><a className="apply-link" href={job.url} target="_blank" rel="noopener noreferrer">Apply ↗</a></div></div></article>;
    }) : <div className="empty-state">No internships match these filters yet. Try a broader search.</div>}</section>
    {pages > 1 && <nav className="pagination" aria-label="Pagination">{page > 1 ? <Link href={pageHref(page - 1)}>← Previous</Link> : <span>← Previous</span>}<span>Page {page} of {pages}</span>{page < pages ? <Link href={pageHref(page + 1)}>Next →</Link> : <span>Next →</span>}</nav>}
  </>;
}
