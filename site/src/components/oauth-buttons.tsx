"use client";

import { createClient } from "@/lib/supabase/client";

export function OAuthButtons({ next = "/" }: { next?: string }) {
  async function signIn(provider: "discord" | "google") {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({ provider, options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` } });
  }
  return <><button className="oauth-button primary" onClick={() => signIn("discord")}><span aria-hidden="true">◉</span> Continue with Discord</button><button className="oauth-button" onClick={() => signIn("google")}><span aria-hidden="true">G</span> Continue with Google</button></>;
}
