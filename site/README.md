# Internship Watcher website

Next.js App Router website for the Internship Watcher, using Supabase Auth and Postgres. Node.js 22 is the supported runtime. The app uses the schema in the repository's ordered Supabase migrations; the existing initialization migration is unchanged.

## Local development

1. Install Node.js 22 and npm.
2. Copy `.env.example` to `.env.local` and set the Supabase project URL and anon key.
3. In Supabase Auth, enable Discord and Google providers and configure their provider credentials.
4. Apply the repository migrations in order, including `supabase/migrations/20261126000200_feed_fn.sql`, which adds the paginated top-company feed RPC.
5. Install dependencies and run the dev server:

   ```sh
   npm install
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000).

The app only uses Supabase's public project URL and publishable key. Row-level security enforces account access. These values are safe to ship to a browser; do not put a service role key in this project or in any `NEXT_PUBLIC_` variable.

## Environment variables

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Public Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public Supabase publishable key (`sb_publishable_…`) |

The example file contains the real public project URL and publishable key. Keep `.env.local` local; it is ignored by git.

## Supabase Auth redirects

In **Supabase Dashboard → Authentication → URL Configuration**, set the Site URL to your local URL while developing (`http://localhost:3000`) or your production Vercel domain after deployment. Add these Redirect URLs so OAuth callback query strings are accepted:

- `http://localhost:3000/**`
- `https://<vercel-domain>/**`
- Your custom domain, if configured: `https://<custom-domain>/**`

For Discord and Google, set each provider's OAuth callback/redirect URI to the Supabase callback URL shown in that provider's Supabase configuration panel. In Supabase Auth provider settings, enable **Allow manual linking** so an existing signed-in account can connect Discord from Settings.

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
