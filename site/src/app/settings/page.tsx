import { createClient } from "@/lib/supabase/server";
import { SettingsForm } from "@/components/settings-form";

export default async function Settings() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  return <><section className="page-heading"><div className="eyebrow">Make it yours</div><h1>Settings</h1><p>Update your profile, alerts, and job preferences.</p></section><SettingsForm userId={user.id} email={user.email ?? ""}/></>;
}
