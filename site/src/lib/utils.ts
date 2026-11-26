export const PAGE_SIZE = 24;
export const statuses = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"] as const;
export function queryText(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] ?? "" : value ?? ""; }
export function splitLines(value: string) { return [...new Set(value.split(/[\n,]/).map((part) => part.trim()).filter(Boolean))]; }
export function dateLabel(value: string | null) { return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—"; }
