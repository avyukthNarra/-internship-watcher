export const PAGE_SIZE = 24;
export const statuses = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"] as const;
export function queryText(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] ?? "" : value ?? ""; }
export function splitLines(value: string) { return [...new Set(value.split(/[\n,]/).map((part) => part.trim()).filter(Boolean))]; }
export function safeNextPath(value: string | null | undefined, origin: string) {
  if (!value || /[\\\u0000-\u001f\u007f]/.test(value)) return null;
  try {
    const decoded = decodeURIComponent(value);
    if (/[\\\u0000-\u001f\u007f]/.test(decoded)) return null;
    const destination = new URL(value, origin);
    if (destination.origin !== new URL(origin).origin) return null;
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return null;
  }
}
export function sanitizeSearch(value: string) { return value.replace(/[(),%*"'\u0000-\u001f\u007f]/g, " ").trim().replace(/\s+/g, " "); }
export function dateLabel(value: string | null) {
  if (!value) return "—";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])) : new Date(value);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
