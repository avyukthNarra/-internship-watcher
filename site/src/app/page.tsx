import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { PAGE_SIZE, queryText, sanitizeSearch } from "@/lib/utils";
import { JobActions } from "@/components/job-actions";
import { FeedTopToggle } from "@/components/feed-top-toggle";
import { NewTodayBadge } from "@/components/new-today-badge";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
const sources = ["greenhouse", "lever", "ashby", "workday", "simplify", "vanshb03", "jobright"];
type FeedJob = { id: string; company: string; title: string; location: string; url: string; terms: string[]; source: string; category: string | null; first_seen: string };

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const query = sanitizeSearch(queryText(params.q));
  const term = queryText(params.term).trim();
  const location = sanitizeSearch(queryText(params.location));
  const source = queryText(params.source).trim();
  const topOnly = queryText(params.top) === "1";
  const page = Math.max(1, Number.parseInt(queryText(params.page) || "1", 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const supabase = await createClient();
  const [{ data: { user }, error: authError }] = await Promise.all([supabase.auth.getUser()]);
  let jobs: FeedJob[] = [];
  let count = 0;
  let feedError: string | null = authError ? "We couldn’t verify your session. Refresh the page and try again." : null;

  if (!feedError && topOnly) {
    const result = await supabase.rpc("top_jobs", {
      p_days: 45,
      p_limit: PAGE_SIZE,
      p_offset: offset,
      p_query: query || null,
      p_term: term || null,
      p_location: location || null,
      p_source: source || null,
    });
    if (result.error) feedError = "We couldn’t load the top-company roles. Please try again.";
    else {
      jobs = result.data.map((row) => ({ id: row.id, company: row.company, title: row.title, location: row.location, url: row.url, terms: row.terms, source: row.source, category: row.category, first_seen: row.first_seen }));
      count = result.data[0]?.total_count ?? 0;
    }
  } else if (!feedError) {
    let request = supabase.from("jobs").select("id,company,title,location,url,terms,source,category,first_seen", { count: "exact" })
      .gte("first_seen", new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString())
      .order("first_seen", { ascending: false }).order("id", { ascending: true })
      .range(offset, offset + PAGE_SIZE - 1);
    if (query) request = request.or(`company.ilike.%${query}%,title.ilike.%${query}%,location.ilike.%${query}%`);
    if (term) request = request.contains("terms", [term]);
    if (location) request = request.ilike("location", `%${location}%`);
    if (source) request = request.eq("source", source);
    const result = await request;
    if (result.error) feedError = "We couldn’t load the job feed. Please try again.";
    else { jobs = result.data; count = result.count ?? 0; }
  }

  const jobIds = jobs.map((job) => job.id);
  let statuses = new Map<string, string>();
  if (user && jobIds.length && !feedError) {
    const statusResult = await supabase.from("user_jobs").select("job_id,status").eq("user_id", user.id).in("job_id", jobIds);
    if (statusResult.error) feedError = "We couldn’t load your saved statuses. Refresh the page and try again.";
    else statuses = new Map(statusResult.data.map((row) => [row.job_id, row.status]));
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const currentParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((entry) => currentParams.append(key, entry));
    else if (value) currentParams.set(key, value);
  }
  const currentHref = `/?${currentParams.toString()}`;
  function pageHref(number: number) {
    const next = new URLSearchParams(currentParams);
    next.set("page", String(number));
    return `/?${next.toString()}`;
  }
  return <>
    <section className="hero"><div><div className="eyebrow">A better start, starts here</div><h1>Find your next<br/>internship.</h1><p>Fresh opportunities for the next generation of builders.</p></div><div className="hero-aside"><strong>{count}</strong> roles in the last 45 days</div></section>
    <form className="filters" action="/" method="get">
      <label className="search-wrap"><span className="search-icon" aria-hidden="true">⌕</span><input className="control" type="search" name="q" defaultValue={query} placeholder="Search roles or companies" aria-label="Search roles or companies" /></label>
      <input className="control" name="term" defaultValue={term} placeholder="Term · e.g. Summer 2027" aria-label="Filter by term" />
      <input className="control" name="location" defaultValue={location} placeholder="Location" aria-label="Filter by location" />
      <select className="control" name="source" defaultValue={source} aria-label="Filter by source"><option value="">All sources</option>{sources.map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}</select>
      {topOnly && <input type="hidden" name="top" value="1" />}<button className="filter-button" type="submit">Search <span aria-hidden="true">↗</span></button>
    </form>
    <div className="feed-toolbar"><span>Showing {count ? offset + 1 : 0}–{Math.min(offset + jobs.length, count)} of {count} roles</span><div className="feed-controls"><FeedTopToggle checked={topOnly} queryString={currentParams.toString()}/>{!user && <Link className="signin-hint" href={`/login?next=${encodeURIComponent(currentHref)}`}>Sign in to save or track</Link>}</div></div>
    {feedError && <p className="error-text" role="alert">{feedError}</p>}
    <section className="job-grid" aria-label="Internship listings">{!feedError && jobs.length ? jobs.map((job) => {
      const initials = job.company.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
      return <article className="job-card" key={job.id}><div className="company-line"><span className="company-logo">{initials}</span><div style={{ minWidth: 0 }}><div className="company-name">{job.company}</div><div className="company-meta">{job.source}</div></div></div><h2 className="job-title">{job.title}</h2><div className="job-location"><span aria-hidden="true">⌖</span>{job.location || "Location not listed"}</div><div className="job-chips">{job.terms.slice(0, 3).map((item) => <span className="chip" key={item}>{item}</span>)}<NewTodayBadge firstSeen={job.first_seen}/></div><div className="job-bottom"><span className="seen">{new Date(job.first_seen).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span><div className="job-actions"><JobActions jobId={job.id} userId={user?.id ?? null} initialStatus={statuses.get(job.id)} nextPath={currentHref}/><a className="apply-link" href={job.url} target="_blank" rel="noopener noreferrer">Apply ↗</a></div></div></article>;
    }) : !feedError ? <div className="empty-state">No internships match these filters yet. Try a broader search.</div> : null}</section>
    {totalPages > 1 && <nav className="pagination" aria-label="Pagination">{page > 1 ? <Link href={pageHref(page - 1)}>← Previous</Link> : <span>← Previous</span>}<span>Page {page} of {totalPages}</span>{page < totalPages ? <Link href={pageHref(page + 1)}>Next →</Link> : <span>Next →</span>}</nav>}
  </>;
}
