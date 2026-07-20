#!/usr/bin/env python3
"""One-off helper: verify candidate ATS board slugs actually exist before
adding them to config.json. Prints OK/FAIL with job counts."""

import json
from concurrent.futures import ThreadPoolExecutor

import requests

HEADERS = {"User-Agent": "internship-watcher/1.0 (personal job alert script)"}

# (display name, ats, slug) — guesses to be verified against live APIs
CANDIDATES = [
    # --- Greenhouse: big tech / public ---
    ("Airbnb", "greenhouse", "airbnb"),
    ("Lyft", "greenhouse", "lyft"),
    ("Instacart", "greenhouse", "instacart"),
    ("Reddit", "greenhouse", "reddit"),
    ("Dropbox", "greenhouse", "dropbox"),
    ("GitLab", "greenhouse", "gitlab"),
    ("MongoDB", "greenhouse", "mongodb"),
    ("Elastic", "greenhouse", "elastic"),
    ("Okta", "greenhouse", "okta"),
    ("Asana", "greenhouse", "asana"),
    ("Twilio", "greenhouse", "twilio"),
    ("Datadog", "greenhouse", "datadog"),
    ("HashiCorp", "greenhouse", "hashicorp"),
    ("Confluent", "greenhouse", "confluent"),
    ("Pure Storage", "greenhouse", "purestorage"),
    ("Snyk", "greenhouse", "snyk"),
    ("Docker", "greenhouse", "docker"),
    ("GitHub", "greenhouse", "github"),
    ("Roblox", "greenhouse", "roblox"),
    # Unity left Greenhouse (Workday now) — covered via the Simplify feed
    ("Epic Games", "greenhouse", "epicgames"),
    ("Niantic", "greenhouse", "niantic"),
    ("Robinhood", "greenhouse", "robinhood"),
    ("Affirm", "greenhouse", "affirm"),
    ("Chime", "greenhouse", "chime"),
    ("Brex", "greenhouse", "brex"),
    ("Gusto", "greenhouse", "gusto"),
    ("Flexport", "greenhouse", "flexport"),
    ("Samsara", "greenhouse", "samsara"),
    ("Benchling", "greenhouse", "benchling"),
    ("Grammarly", "greenhouse", "grammarly"),
    ("Airtable", "greenhouse", "airtable"),
    ("Retool", "greenhouse", "retool"),
    ("Vercel", "greenhouse", "vercel"),
    ("Squarespace", "greenhouse", "squarespace"),
    ("Whatnot", "greenhouse", "whatnot"),
    ("Faire", "greenhouse", "faire"),
    ("Snap", "greenhouse", "snapchat"),
    ("Block (Square)", "greenhouse", "block"),
    # --- Greenhouse: AI labs / AI infra ---
    ("xAI", "greenhouse", "xai"),
    ("Character.AI", "greenhouse", "character"),
    ("Runway", "greenhouse", "runwayml"),
    ("Stability AI", "greenhouse", "stabilityai"),
    ("Groq", "greenhouse", "groq"),
    ("SambaNova", "greenhouse", "sambanovasystems"),
    ("Lambda", "greenhouse", "lambda"),
    ("Pinecone", "greenhouse", "pinecone"),
    ("Glean", "greenhouse", "gleanwork"),
    ("Anyscale", "greenhouse", "anyscale"),
    ("Deepgram", "greenhouse", "deepgram"),
    ("AssemblyAI", "greenhouse", "assemblyai"),
    ("Hugging Face", "greenhouse", "huggingface"),
    ("Luma AI", "greenhouse", "lumaai"),
    ("Mistral AI (GH)", "greenhouse", "mistral"),
    # --- Greenhouse: autonomy / aerospace / robotics ---
    ("Waymo", "greenhouse", "waymo"),
    ("Cruise", "greenhouse", "cruise"),
    ("Nuro", "greenhouse", "nuro"),
    ("Aurora", "greenhouse", "aurorainnovation"),
    ("SpaceX", "greenhouse", "spacex"),
    ("Anduril", "greenhouse", "andurilindustries"),
    ("Relativity Space", "greenhouse", "relativityspace"),
    ("Neuralink", "greenhouse", "neuralink"),
    ("Boston Dynamics", "greenhouse", "bostondynamics"),
    ("Skydio", "greenhouse", "skydio"),
    ("Figure", "greenhouse", "figureai"),
    # --- Greenhouse: quant / fintech ---
    ("Hudson River Trading", "greenhouse", "wehrtyou"),
    ("Jump Trading", "greenhouse", "jumptrading"),
    ("IMC Trading", "greenhouse", "imc"),
    ("Akuna Capital", "greenhouse", "akunacapital"),
    ("Point72", "greenhouse", "point72"),
    ("Two Sigma", "greenhouse", "twosigma"),
    ("Optiver", "greenhouse", "optiverus"),
    ("DRW", "greenhouse", "drw"),
    ("Five Rings", "greenhouse", "fiverings"),
    ("Tower Research", "greenhouse", "towerresearchcapital"),
    ("Virtu Financial", "greenhouse", "virtu"),
    # --- Lever ---
    ("Zoox", "lever", "zoox"),
    ("Weights & Biases", "lever", "wandb"),
    ("Cerebras", "ashby", "cerebras"),
    ("Canva", "lever", "canva"),
    ("Atlassian", "lever", "atlassian"),
    ("Shield AI", "lever", "shieldai"),
    ("Voleon", "lever", "voleon"),
    ("Kodiak Robotics", "lever", "kodiak"),
    ("Spotify", "lever", "spotify"),
    ("Netflix (Lever)", "lever", "netflix"),
    ("1Password", "lever", "1password"),
    ("Five Rings (Lever)", "lever", "five-rings"),
    # --- Ashby ---
    ("Modal", "ashby", "modal"),
    ("Supabase", "ashby", "supabase"),
    ("Linear", "ashby", "linear"),
    ("LangChain", "ashby", "langchain"),
    ("Harvey", "ashby", "harvey"),
    ("Sierra", "ashby", "sierra"),
    ("Decagon", "ashby", "decagon"),
    ("Mercor", "ashby", "mercor"),
    ("Suno", "ashby", "suno"),
    ("Baseten", "ashby", "baseten"),
    ("Fireworks AI", "ashby", "fireworksai"),
    ("Replicate", "ashby", "replicate"),
    ("Deel", "ashby", "deel"),
    ("Vanta", "ashby", "vanta"),
    ("Zip", "ashby", "zip"),
    ("OpenEvidence", "ashby", "openevidence"),
    ("Physical Intelligence", "ashby", "physicalintelligence"),
    ("Thinking Machines", "ashby", "thinking-machines"),
    ("Character.AI (Ashby)", "ashby", "character"),
    ("Hugging Face (Ashby)", "ashby", "huggingface"),
    ("Figure (Ashby)", "ashby", "figure"),
    ("Anysphere (Cursor alt)", "ashby", "anysphere"),
    ("Scale AI (Ashby)", "ashby", "scaleai"),
    ("Windsurf", "ashby", "windsurf"),
    ("Lovable", "ashby", "lovable"),
    ("Clay", "ashby", "clay"),
    ("Browserbase", "ashby", "browserbase"),
    ("Cognition", "ashby", "cognition"),
    ("EvenUp", "ashby", "evenup"),
    ("Abridge", "ashby", "abridge"),
    # --- batch 2 (2026-06): more AI startups + quant, verified live ---
    ("Apptronik", "greenhouse", "apptronik"),
    ("Arize AI", "greenhouse", "arizeai"),
    ("CoreWeave", "greenhouse", "coreweave"),
    ("Cresta", "greenhouse", "cresta"),
    ("Helsing", "greenhouse", "helsing"),
    ("Imbue", "greenhouse", "imbue"),
    ("Labelbox", "greenhouse", "labelbox"),
    ("Lightning AI", "greenhouse", "lightningai"),
    ("Snorkel AI", "greenhouse", "snorkelai"),
    ("Tenstorrent", "greenhouse", "tenstorrent"),
    ("Wayve", "greenhouse", "wayve"),
    ("Black Forest Labs", "greenhouse", "blackforestlabs"),
    ("Cohere Health", "greenhouse", "coherehealth"),
    ("HeyGen", "greenhouse", "heygen"),
    ("Vannevar Labs", "greenhouse", "vannevarlabs"),
    ("World Labs", "greenhouse", "worldlabs"),
    ("Galileo", "greenhouse", "galileo"),
    ("Kodiak Robotics", "greenhouse", "kodiak"),
    ("Jane Street", "greenhouse", "janestreet"),
    ("Old Mission", "greenhouse", "oldmissioncapital"),
    ("PDT Partners", "greenhouse", "pdtpartners"),
    ("Schonfeld", "greenhouse", "schonfeld"),
    ("Squarepoint", "greenhouse", "squarepointcapital"),
    ("WorldQuant", "greenhouse", "worldquant"),
    ("Ambience Healthcare", "ashby", "ambiencehealthcare"),
    ("Artisan", "ashby", "artisan"),
    ("Braintrust", "ashby", "braintrust"),
    ("Cartesia", "ashby", "cartesia"),
    ("Chroma", "ashby", "trychroma"),
    ("Dust", "ashby", "dust"),
    ("Etched", "ashby", "etched"),
    ("Ideogram", "ashby", "ideogram"),
    ("Krea", "ashby", "krea"),
    ("Pika", "ashby", "pika"),
    ("Poolside", "ashby", "poolside"),
    ("Reka AI", "ashby", "reka"),
    ("Saronic", "ashby", "saronic"),
    ("Synthesia", "ashby", "synthesia"),
    ("Tavus", "ashby", "tavus"),
    ("Vapi", "ashby", "vapi"),
    ("Weaviate", "ashby", "weaviate"),
    ("Writer", "ashby", "writer"),
    ("Distyl AI", "ashby", "distyl"),
    ("Replit", "ashby", "replit"),
    ("Runway", "ashby", "runway"),
    ("Voleon", "ashby", "voleon"),
    ("Liquid AI", "ashby", "liquid"),
    ("Sword Health", "lever", "swordhealth"),
    # --- batch 3 (2026-07): broad "best SWE companies" expansion ---
    # quant / trading
    ("Citadel", "greenhouse", "citadel"),
    ("Citadel Securities", "greenhouse", "citadelsecurities"),
    ("SIG (Susquehanna)", "greenhouse", "sig"),
    ("Belvedere Trading", "greenhouse", "belvederetrading"),
    ("Chicago Trading Company", "greenhouse", "chicagotradingcompany"),
    ("Wolverine Trading", "greenhouse", "wolverinetrading"),
    ("XTX Markets", "greenhouse", "xtxmarkets"),
    ("Flow Traders", "greenhouse", "flowtraders"),
    ("Two Sigma (retry)", "greenhouse", "twosigma"),
    # fintech
    ("Rippling", "greenhouse", "rippling"),
    ("Carta", "greenhouse", "carta"),
    ("Mercury", "greenhouse", "mercury"),
    ("SoFi", "greenhouse", "sofi"),
    ("Adyen", "greenhouse", "adyen"),
    ("Wise", "greenhouse", "transferwise"),
    ("Gemini (crypto)", "greenhouse", "gemini"),
    ("Ripple", "greenhouse", "ripple"),
    ("Kraken", "lever", "kraken"),
    # dev tools / infra
    ("Sentry", "greenhouse", "sentry"),
    ("Sourcegraph", "greenhouse", "sourcegraph"),
    ("Grafana Labs", "greenhouse", "grafanalabs"),
    ("Temporal", "greenhouse", "temporaltechnologies"),
    ("dbt Labs", "greenhouse", "dbtlabsinc"),
    ("Postman", "greenhouse", "postman"),
    ("Cockroach Labs", "greenhouse", "cockroachlabs"),
    ("Chronosphere", "greenhouse", "chronosphere"),
    ("PostHog", "ashby", "posthog"),
    ("Railway", "ashby", "railway"),
    ("Render", "ashby", "render"),
    ("Warp", "ashby", "warpdotdev"),
    # security
    ("Wiz", "greenhouse", "wizinc"),
    ("Tailscale", "greenhouse", "tailscale"),
    # autonomy / hardware / product
    ("Applied Intuition", "greenhouse", "appliedintuition"),
    ("Verkada", "greenhouse", "verkada"),
    ("Zipline", "greenhouse", "flyzipline"),
    ("Turo", "greenhouse", "turo"),
    ("Strava", "lever", "strava"),
    ("Quora", "ashby", "quora"),
    ("Snap (retry)", "greenhouse", "snap"),
    ("Groq (retry)", "greenhouse", "groqinc"),
    ("Thinking Machines (retry)", "ashby", "thinkingmachines"),
]


def check(c):
    name, ats, slug = c
    try:
        if ats == "greenhouse":
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                headers=HEADERS, timeout=15)
            n = len(r.json().get("jobs", [])) if r.status_code == 200 else -1
        elif ats == "lever":
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=HEADERS, timeout=15)
            d = r.json() if r.status_code == 200 else None
            n = len(d) if isinstance(d, list) else -1
        else:
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                headers=HEADERS, timeout=15)
            n = len(r.json().get("jobs", [])) if r.status_code == 200 else -1
    except Exception:
        n = -1
    return (name, ats, slug, n)


with ThreadPoolExecutor(max_workers=16) as ex:
    results = list(ex.map(check, CANDIDATES))

ok = [r for r in results if r[3] >= 0]
fail = [r for r in results if r[3] < 0]
print(f"--- VERIFIED ({len(ok)}) ---")
for name, ats, slug, n in sorted(ok, key=lambda r: (r[1], r[0])):
    print(f"  {ats:10s} {slug:25s} {name:25s} {n} jobs")
print(f"--- FAILED ({len(fail)}) ---")
for name, ats, slug, n in sorted(fail, key=lambda r: (r[1], r[0])):
    print(f"  {ats:10s} {slug:25s} {name}")
