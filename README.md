# yt-autoposter

Daily YouTube Short generated with [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) and uploaded automatically via GitHub Actions.

## Setup

1. **Add repository secrets**: Repo Settings -> Secrets and variables -> Actions -> add:
   - `GEMINI_API_KEY` (required) - Google AI Studio API key
   - `PEXELS_API_KEY` or `PIXABAY_API_KEY` (at least one required) - stock video source
   - `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` (optional) - for YouTube upload
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional) - for Telegram delivery
   - `GEMINI_MODEL` (optional) - overrides the default Gemini model (default: `gemini-2.0-flash`)
   - `OPENAI_API_KEY` (optional) - only if you set `LLM_PROVIDER=openai`

2. **Edit topics** in `run_daily.py` (`TOPICS` list).

3. **Edit schedule** in `.github/workflows/daily-short.yml` (`cron`, UTC time).

4. **Test**: Run it once from the Actions tab (Run workflow).

Uploads are private by default. Change `PRIVACY` in `run_daily.py` to `"public"` when ready.

## Troubleshooting

- **Gemini 429 / quota exhausted**: set the `GEMINI_MODEL` secret to a model with available quota (e.g. `gemini-2.0-flash` or another flash model) or check your [AI Studio quota](https://ai.dev/rate-limit).
- **No video source**: provide at least one of `PEXELS_API_KEY` or `PIXABAY_API_KEY`.
- **YouTube upload fails**: verify OAuth credentials and refresh token; uploads are skipped unless `YT_REFRESH_TOKEN` is set.
