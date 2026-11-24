# yt-autoposter

Daily YouTube Short generated with MoneyPrinterTurbo and uploaded automatically via GitHub Actions.

## Setup
1. Repo Settings -> Secrets and variables -> Actions -> add:
   OPENAI_API_KEY, PEXELS_API_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
2. Edit TOPICS in run_daily.py.
3. Edit the cron line in .github/workflows/daily-short.yml (UTC time).
4. Run it once from the Actions tab (Run workflow) to test.

Uploads are private by default. Change PRIVACY in run_daily.py to "public" when ready.
