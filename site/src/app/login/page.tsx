import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { OAuthButtons } from "@/components/oauth-buttons";

export default async function Login({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next = "/" } = await searchParams;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (user) redirect(next.startsWith("/") && !next.startsWith("//") ? next : "/");
  return <section className="login-card"><div className="eyebrow">Your next chapter</div><h1>Sign in to get started.</h1><p>Save roles, track applications, and keep your search in one place.</p><OAuthButtons next={next} /><p style={{ marginTop: 18, fontSize: 11 }}>By continuing, you agree to use Internship Watcher responsibly.</p></section>;
}
