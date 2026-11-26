# Internship Watcher website

Next.js App Router website for the Internship Watcher, using Supabase Auth and Postgres. Node.js 22 is the supported runtime. Keep all database schema changes in the existing repository migration; this app expects that schema as written.

## Local development

1. Install Node.js 22 and npm.
2. Copy `.env.example` to `.env.local` and set the Supabase project URL and anon key.
3. In Supabase Auth, enable Discord and Google providers and configure their provider credentials.
4. Install dependencies and run the dev server:

   ```sh
   npm install
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000).

The app only uses the public anon key. Row-level security enforces account access. Do not put a service role key in this project or in any `NEXT_PUBLIC_` variable.

## Environment variables

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL, such as `https://your-project.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |

The example file contains placeholders only. The app builds with placeholder values, but database and OAuth actions require a real Supabase project at runtime.

## Supabase Auth redirects

In **Supabase Dashboard → Authentication → URL Configuration**, set the Site URL to your local URL while developing (`http://localhost:3000`) or your production Vercel domain after deployment. Add these Redirect URLs:

- `http://localhost:3000/auth/callback`
- `https://YOUR-PROJECT.vercel.app/auth/callback`
- Your custom-domain callback URL, if configured: `https://YOUR-DOMAIN/auth/callback`

For Discord and Google, also set each provider's OAuth callback/redirect URI to the Supabase callback URL shown in that provider's Supabase configuration panel (commonly `https://YOUR-PROJECT.supabase.co/auth/v1/callback`).

## Vercel deployment

Import the GitHub repository into Vercel and configure:

- **Root Directory:** `site`
- **Framework Preset:** Next.js
- **Node.js Version:** 22.x
- **Install Command:** `npm install` (or leave the default)
- **Build Command:** `npm run build`
- **Output Directory:** leave blank/default for Next.js

Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in Vercel Project Settings → Environment Variables for Preview and Production (and Development if using Vercel CLI). Add the production Vercel callback URL to Supabase Auth Redirect URLs, then redeploy after changing environment values.

## Scripts

- `npm run dev` — local development
- `npm run build` — production build
- `npm run start` — serve a production build
- `npm run lint` — ESLint
