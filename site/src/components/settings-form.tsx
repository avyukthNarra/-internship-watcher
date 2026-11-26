"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { splitLines } from "@/lib/utils";

type Preferences = { roles: string[]; locations: string[]; terms: string[]; exclude_roles: string[]; categories: string[]; keep_unknown_terms: boolean; only_top_companies: boolean; follow_up_days: number };
type Profile = { display_name: string | null; notify_dm: boolean; notify_email: boolean; discord_user_id: string | null };
type Override = { company: string; action: "add" | "remove" };
type PrefField = "roles" | "locations" | "terms" | "exclude_roles" | "categories";
const emptyPrefs: Preferences = { roles: [], locations: [], terms: [], exclude_roles: [], categories: [], keep_unknown_terms: true, only_top_companies: true, follow_up_days: 14 };

export function SettingsForm({ userId, email }: { userId: string; email: string }) {
  const [prefs, setPrefs] = useState(emptyPrefs);
  const [profile, setProfile] = useState<Profile>({ display_name: "", notify_dm: false, notify_email: false, discord_user_id: null });
  const [defaults, setDefaults] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [search, setSearch] = useState("");
  const [custom, setCustom] = useState("");
  const [rawText, setRawText] = useState<Record<PrefField, string>>({ roles: "", locations: "", terms: "", exclude_roles: "", categories: "" });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => {
    async function load() {
      const supabase = createClient();
      try {
        const [p, f, d, o] = await Promise.all([
          supabase.from("profiles").select("display_name,notify_dm,notify_email,discord_user_id").eq("user_id", userId).single(),
          supabase.from("user_preferences").select("roles,locations,terms,exclude_roles,categories,keep_unknown_terms,only_top_companies,follow_up_days").eq("user_id", userId).single(),
          supabase.from("default_top_companies").select("name").order("name").limit(1000),
          supabase.from("user_top_company_overrides").select("company,action").eq("user_id", userId).limit(1000),
        ]);
        const failures = [p.error, f.error, d.error, o.error].filter((item) => item !== null);
        if (failures.length) {
          setLoadError(`Settings could not be loaded: ${failures.map((item) => item.message).join("; ")}`);
          return;
        }
        if (!p.data || !f.data) {
          setLoadError("Your profile or preferences are missing. Refresh the page or sign in again.");
          return;
        }
        setProfile(p.data);
        setPrefs(f.data);
        setRawText({ roles: f.data.roles.join("\n"), locations: f.data.locations.join("\n"), terms: f.data.terms.join("\n"), exclude_roles: f.data.exclude_roles.join("\n"), categories: f.data.categories.join("\n") });
        setDefaults((d.data ?? []).map((item) => item.name));
        setOverrides(o.data ?? []);
      } catch {
        setLoadError("Settings could not be loaded. Check your connection and try again.");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [userId]);
  async function saveAll() {
    if (loading || loadError) return;
    setError(""); setMessage("");
    const supabase = createClient();
    const preferences = { ...prefs, roles: splitLines(rawText.roles), locations: splitLines(rawText.locations), terms: splitLines(rawText.terms), exclude_roles: splitLines(rawText.exclude_roles), categories: splitLines(rawText.categories) };
    const [p, f] = await Promise.all([
      supabase.from("profiles").update({ display_name: profile.display_name || null, notify_dm: profile.notify_dm, notify_email: profile.notify_email }).eq("user_id", userId).select("user_id"),
      supabase.from("user_preferences").update(preferences).eq("user_id", userId).select("user_id"),
    ]);
    if (p.error || f.error) setError(p.error?.message ?? f.error?.message ?? "Could not save settings.");
    else if (!p.data?.length || !f.data?.length) setError("No settings row was updated. Refresh and try again.");
    else { setPrefs(preferences); setMessage("Your settings are saved."); }
  }
  async function setOverride(company: string, action: "add" | "remove") {
    setError("");
    const { error: dbError } = await createClient().from("user_top_company_overrides").upsert({ user_id: userId, company, action }, { onConflict: "user_id,company" }).select("company");
    if (dbError) { setError(dbError.message); return false; }
    setOverrides((current) => [...current.filter((entry) => entry.company !== company), { company, action }]);
    return true;
  }
  async function deleteOverride(company: string) {
    setError("");
    const { error: dbError } = await createClient().from("user_top_company_overrides").delete().eq("user_id", userId).eq("company", company).select("company");
    if (dbError) { setError(dbError.message); return false; }
    setOverrides((current) => current.filter((entry) => entry.company !== company));
    return true;
  }
  async function resetCompanies() {
    const { error: dbError } = await createClient().from("user_top_company_overrides").delete().eq("user_id", userId).select("company");
    if (dbError) setError(dbError.message); else { setOverrides([]); setMessage("Top companies reset to the default list."); }
  }
  async function connectDiscord() {
    const { error: authError } = await createClient().auth.linkIdentity({ provider: "discord", options: { redirectTo: `${window.location.origin}/auth/callback?next=/settings` } });
    if (authError) setError(authError.message);
  }
  async function signOut() {
    const { error: signOutError } = await createClient().auth.signOut();
    if (signOutError) setError(signOutError.message);
    else { router.push("/"); router.refresh(); }
  }
  function textField(label: string, field: PrefField, hint: string) {
    return <label className="field-label">{label}<textarea className="settings-area" value={rawText[field]} onChange={(event) => setRawText({ ...rawText, [field]: event.target.value })} placeholder={hint} /></label>;
  }
  const filteredDefaults = defaults.filter((name) => name.toLowerCase().includes(search.toLowerCase())).slice(0, 80);
  const customAdded = overrides.filter((entry) => entry.action === "add");
  if (loading) return <p className="muted" role="status">Loading your settings…</p>;
  if (loadError) return <section className="settings-section"><p className="error-text" role="alert">{loadError}</p><button className="ghost-button" onClick={() => window.location.reload()}>Retry</button></section>;
  return <><div className="feed-toolbar" style={{ paddingTop: 0 }}><span>{email}</span><button className="ghost-button" onClick={signOut}>Sign out</button></div>{message && <p className="alert" role="status">{message}</p>}{error && <p className="error-text" role="alert">{error}</p>}<div className="settings-grid">
    <section className="settings-section"><h2>Profile & notifications</h2><p>Choose how we keep in touch.</p><label className="field-label">Display name<input className="settings-input" value={profile.display_name ?? ""} onChange={(e) => setProfile({ ...profile, display_name: e.target.value })} placeholder="Your name" /></label><label className="settings-check"><input type="checkbox" checked={profile.notify_dm} onChange={(e) => setProfile({ ...profile, notify_dm: e.target.checked })}/> Send me Discord DMs about matching roles</label><label className="settings-check"><input type="checkbox" checked={profile.notify_email} onChange={(e) => setProfile({ ...profile, notify_email: e.target.checked })}/> Send me email alerts</label><div className="muted">Discord account: {profile.discord_user_id ? `Linked · ${profile.discord_user_id}` : "Not linked"}</div>{!profile.discord_user_id && <button className="ghost-button" style={{ marginTop: 10 }} onClick={connectDiscord}>Connect Discord ↗</button>}</section>
    <section className="settings-section"><h2>Role preferences</h2><p>These help match opportunities to your interests.</p>{textField("Roles", "roles", "Software engineering, Product…")}{textField("Locations", "locations", "Remote, Austin, New York…")}{textField("Terms", "terms", "Summer 2027, Fall 2026…")}{textField("Exclude roles", "exclude_roles", "Senior, PhD required…")}{textField("Categories", "categories", "Engineering, Design…")}<label className="settings-check"><input type="checkbox" checked={prefs.keep_unknown_terms} onChange={(e) => setPrefs({ ...prefs, keep_unknown_terms: e.target.checked })}/> Include jobs without a recognized term</label><label className="settings-check"><input type="checkbox" checked={prefs.only_top_companies} onChange={(e) => setPrefs({ ...prefs, only_top_companies: e.target.checked })}/> Alert me about top companies only</label><label className="field-label">Follow up after (days)<input className="settings-input" type="number" min="0" max="365" value={prefs.follow_up_days} onChange={(e) => setPrefs({ ...prefs, follow_up_days: Number(e.target.value) })}/></label></section>
    <section className="settings-section" style={{ gridColumn: "1 / -1" }}><h2>Your top companies</h2><p>Default companies stay in sync with the watcher. Add your own or hide defaults for your account.</p><input className="settings-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search default companies" aria-label="Search companies"/><div className="company-list">{filteredDefaults.map((company) => { const override = overrides.find((item) => item.company === company); const removed = override?.action === "remove"; return <div className="company-row" key={company}><span>{company}<small>{removed ? "Hidden" : "Default"}</small></span><button onClick={() => removed ? deleteOverride(company) : setOverride(company, "remove")}>{removed ? "Restore" : "Remove"}</button></div>; })}{filteredDefaults.length === 0 && <div className="company-row">No matching defaults.</div>}{customAdded.filter((entry) => !defaults.some((name) => name.toLowerCase() === entry.company.toLowerCase())).map((entry) => <div className="company-row" key={entry.company}><span>{entry.company}<small>Custom</small></span><button onClick={() => deleteOverride(entry.company)}>Remove</button></div>)}</div><div className="inline-input" style={{ marginTop: 10 }}><input className="settings-input" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Add a company"/><button className="secondary-button" onClick={async () => { const name = custom.trim(); if (name && name.length <= 200 && await setOverride(name, "add")) setCustom(""); else if (name.length > 200) setError("Company names must be 200 characters or fewer."); }}>Add</button></div><div className="form-footer"><button className="ghost-button" onClick={resetCompanies}>Reset to default</button><span className="muted">New default companies will appear automatically.</span></div></section>
    <div className="form-footer" style={{ gridColumn: "1 / -1", justifyContent: "flex-end" }}><button className="primary-button" onClick={saveAll}>Save settings</button></div>
  </div></>;
}
