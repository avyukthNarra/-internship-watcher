import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  if (code) await (await createClient()).auth.exchangeCodeForSession(code);
  const destination = url.searchParams.get("next") ?? "/";
  const safeDestination = destination.startsWith("/") && !destination.startsWith("//") ? destination : "/";
  return NextResponse.redirect(new URL(safeDestination, url.origin));
}
