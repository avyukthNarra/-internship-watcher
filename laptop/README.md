# Windows Workday fetcher

The laptop needs Python, Git, this public code, and a write-only-purpose SSH deploy key for the private results repository. It does not need Discord, Notion, or watcher state secrets.

1. Install Python 3.12 from python.org (enable the Python launcher) and Git for Windows from git-scm.com. Open PowerShell and check `py -3.12 --version` and `git --version`.
2. Clone the watcher and the owner's private results repo as sibling folders. Replace the owner and repo names as needed:
   ```powershell
   git clone https://github.com/avyukthNarra/-internship-watcher.git
   git clone git@github.com:OWNER/internship-watcher-workday.git
   py -3.12 -m pip install -r .\-internship-watcher\requirements.txt
   ```
   Generate and register the key before the private clone if it does not yet exist:
   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\workday_results" -C "workday-laptop"
   Get-Content "$env:USERPROFILE\.ssh\workday_results.pub"
   ```
   Give the public key to the owner for a **write-enabled deploy key** on the private results repo. Configure `~/.ssh/config` with a dedicated host alias so only this clone uses that key:
   ```text
   Host github-workday
       HostName github.com
       User git
       IdentityFile ~/.ssh/workday_results
       IdentitiesOnly yes
   ```
   Clone with `git clone git@github-workday:OWNER/internship-watcher-workday.git` (or change the clone's origin to that URL). Use Windows OpenSSH agent to load the key if it has a passphrase; the scheduled user must be able to use it unattended.
3. Set Windows power settings to **never sleep while plugged in** and set closing the lid to **do nothing** on AC. In Dell Power Manager or My Dell, select **Primarily AC Use** for battery charging if available. Keep the laptop plugged in and connected to home Wi-Fi.
4. Test fetching and publishing (no watcher notification secrets required):
   ```powershell
   cd .\-internship-watcher
   py -3.12 workday_fetch.py --dry-run
   py -3.12 workday_fetch.py --push ..\internship-watcher-workday
   .\laptop\run_workday.ps1
   .\laptop\install_task.ps1
   ```
   For different paths or a differently named private repo, pass `-WatcherDir` and `-ResultsDir` to both scripts. Task Scheduler prompts for the Windows account password for running while logged off. Use an account permitted to log on as a batch job.
5. In Task Scheduler, run **InternshipWatcherWorkday** once, inspect Last Run Result and `laptop\workday.log`, and confirm `workday_jobs.json` and a recent commit in the private repo. Logs rotate at 1 MB with five backups. Run `laptop\uninstall_task.ps1` to remove the task.

Quick connectivity check (a response other than 429/Cloudflare HTML indicates a reachable endpoint; this sends one real search request):
```powershell
Invoke-WebRequest -Method Post -Uri 'https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs' -ContentType 'application/json' -Body '{"appliedFacets":{},"limit":20,"offset":0,"searchText":"intern"}'
```
