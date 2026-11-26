import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { OAuthButtons } from "@/components/oauth-buttons";
import { safeNextPath } from "@/lib/utils";

export default async function Login({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const params = await searchParams;
  const next = safeNextPath(params.next, "http://localhost") ?? "/";
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (user) redirect(next);
  return <section className="login-card"><div className="eyebrow">Your next chapter</div><h1>Sign in to get started.</h1><p>Save roles, track applications, and keep your search in one place.</p>{params.error && <p className="alert" role="alert">Sign-in could not be completed. Please try again.</p>}<OAuthButtons next={next} /><p style={{ marginTop: 18, fontSize: 11 }}>By continuing, you agree to use Internship Watcher responsibly.</p></section>;
}
