-- Paginated top-company feed. Dynamic SQL avoids referencing the authenticated
-- user view for anon callers, who intentionally have no SELECT grant on it.
create or replace function public.top_jobs(
  p_days int,
  p_limit int,
  p_offset int,
  p_query text,
  p_term text,
  p_location text,
  p_source text
)
returns table (
  id text,
  company text,
  title text,
  location text,
  url text,
  terms text[],
  source text,
  category text,
  first_seen timestamptz,
  total_count bigint
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  days int := greatest(0, least(coalesce(p_days, 45), 3650));
  page_size int := greatest(1, least(coalesce(p_limit, 24), 100));
  page_offset int := greatest(coalesce(p_offset, 0), 0);
begin
  if (select auth.uid()) is null then
    return query execute $query$
      select j.id, j.company, j.title, j.location, j.url, j.terms, j.source, j.category, j.first_seen, count(*) over ()
        from public.jobs j
       where j.first_seen >= now() - make_interval(days => $1)
         and exists (select 1 from public.default_top_companies c where lower(c.name) = lower(j.company))
         and ($4 is null or j.company ilike '%' || $4 || '%' or j.title ilike '%' || $4 || '%' or j.location ilike '%' || $4 || '%')
         and ($5 is null or j.terms @> array[$5]::text[])
         and ($6 is null or j.location ilike '%' || $6 || '%')
         and ($7 is null or j.source = $7)
       order by j.first_seen desc, j.id asc
       limit $2 offset $3
    $query$ using days, page_size, page_offset, p_query, p_term, p_location, p_source;
  else
    return query execute $query$
      select j.id, j.company, j.title, j.location, j.url, j.terms, j.source, j.category, j.first_seen, count(*) over ()
        from public.jobs j
       where j.first_seen >= now() - make_interval(days => $1)
         and exists (select 1 from public.user_top_companies c where c.user_id = (select auth.uid()) and lower(c.company) = lower(j.company))
         and ($4 is null or j.company ilike '%' || $4 || '%' or j.title ilike '%' || $4 || '%' or j.location ilike '%' || $4 || '%')
         and ($5 is null or j.terms @> array[$5]::text[])
         and ($6 is null or j.location ilike '%' || $6 || '%')
         and ($7 is null or j.source = $7)
       order by j.first_seen desc, j.id asc
       limit $2 offset $3
    $query$ using days, page_size, page_offset, p_query, p_term, p_location, p_source;
  end if;
end
$$;
