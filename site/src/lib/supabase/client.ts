import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "@/lib/database.types";

function getSupabaseEnv() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url) throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL environment variable.");
  if (!key) throw new Error("Missing NEXT_PUBLIC_SUPABASE_ANON_KEY environment variable.");
  return { url, key };
}

export function createClient() {
  const { url, key } = getSupabaseEnv();
  return createBrowserClient<Database>(url, key);
}
