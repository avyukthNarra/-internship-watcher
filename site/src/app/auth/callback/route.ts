import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNextPath } from "@/lib/utils";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  if (!code) return NextResponse.redirect(new URL("/login?error=Sign-in%20could%20not%20be%20completed.%20Please%20try%20again.", url.origin));
  const { error } = await (await createClient()).auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(new URL("/login?error=Sign-in%20could%20not%20be%20completed.%20Please%20try%20again.", url.origin));
  const destination = safeNextPath(url.searchParams.get("next"), url.origin) ?? "/";
  return NextResponse.redirect(new URL(destination, url.origin));
}
