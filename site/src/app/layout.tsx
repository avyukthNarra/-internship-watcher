import type { Metadata } from "next";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import "./globals.css";

export const metadata: Metadata = { title: "Internship Watcher", description: "Find your next internship." };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  return <html lang="en"><body><div className="shell">
    <header className="topbar"><Link href="/" className="wordmark"><span className="mark">iw</span> internship watcher</Link><nav aria-label="Main navigation"><Link href="/">Explore</Link>{user && <><Link href="/tracker">Tracker</Link><Link href="/settings">Settings</Link></>}{user ? <span className="nav-user">{user.user_metadata?.name ?? user.email}</span> : <Link className="nav-login" href="/login">Sign in <span aria-hidden="true">↗</span></Link>}</nav></header>
    <main>{children}</main><footer><span>Made for the next step.</span><span>New roles, every day <i className="live-dot" /></span></footer>
  </div></body></html>;
}
