"""Daily pipeline: MoneyPrinterTurbo -> final.mp4 -> Telegram (and optional YouTube upload).

Runs the same way in Google Colab (keys from the Secrets panel) and in
GitHub Actions (keys from repository secrets, passed as environment variables).
"""
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT / "MoneyPrinterTurbo"
API = "http://127.0.0.1:8080"
OUT = ROOT / "final.mp4"
TELEGRAM_LIMIT = 49 * 1024 * 1024  # bots can send files up to 50 MB

# ---- EDIT THESE -------------------------------------------------------------
TOPICS = [
    "3 surprising facts about the human brain",
    "Why the ocean is salty",
    "How black holes are formed",
    "Habits of highly productive people",
    "The history of the internet in 60 seconds",
]
PRIVACY = "private"        # YouTube upload only. Use "public" once you trust the output.
CATEGORY_ID = "27"         # YouTube category, 27 = Education
VOICE = "en-US-AriaNeural-Female"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"   # override with a GEMINI_MODEL secret/env
# -----------------------------------------------------------------------------


def env(key, default=""):
    """Read a secret from Colab Secrets first, then from environment variables."""
    try:
        from google.colab import userdata
        value = userdata.get(key)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(key, default)


# ---------------------------------------------------------------- config ----
def set_key(text, key, literal):
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
    if not pattern.search(text):
        print(f"WARNING: config key '{key}' not found in config.example.toml")
        return text
    return pattern.sub(lambda m: f"{key} = {literal}", text, count=1)


def build_config(example_text):
    provider = env("LLM_PROVIDER", "gemini")
    pexels = env("PEXELS_API_KEY")
    pixabay = env("PIXABAY_API_KEY")

    if provider == "gemini" and not env("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is missing. Add it as a secret.")
    if not (pexels or pixabay):
        raise RuntimeError("Add PIXABAY_API_KEY (or PEXELS_API_KEY) as a secret.")

    cfg = set_key(example_text, "llm_provider", json.dumps(provider))
    if provider == "gemini":
        cfg = set_key(cfg, "gemini_api_key", json.dumps(env("GEMINI_API_KEY")))
        cfg = set_key(cfg, "gemini_model_name", json.dumps(env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)))
    if env("OPENAI_API_KEY"):
        cfg = set_key(cfg, "openai_api_key", json.dumps(env("OPENAI_API_KEY")))
    if pexels:
        cfg = set_key(cfg, "pexels_api_keys", json.dumps([pexels]))
    if pixabay:
        cfg = set_key(cfg, "pixabay_api_keys", json.dumps([pixabay]))
    cfg = set_key(cfg, "video_source", json.dumps("pexels" if pexels else "pixabay"))
    return cfg


def setup():
    if not REPO.exists():
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/harry0703/MoneyPrinterTurbo.git", str(REPO)], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                        str(REPO / "requirements.txt")], check=True)
    example = (REPO / "config.example.toml").read_text(encoding="utf-8")
    (REPO / "config.toml").write_text(build_config(example), encoding="utf-8")


# ---------------------------------------------------------------- server ----
def start_server():
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=REPO)
    for _ in range(90):
        if proc.poll() is not None:
            raise RuntimeError("MoneyPrinterTurbo server exited during startup (see log above)")
        try:
            requests.get(f"{API}/docs", timeout=2)
            return proc
        except Exception:
            time.sleep(2)
    proc.terminate()
    raise RuntimeError("MoneyPrinterTurbo API did not start in time")


FAILED_STATES = {-1, "-1", "failed", "error"}


def fetch_video(task_id, videos):
    """Copy the finished video to final.mp4 (disk first, then the HTTP URL)."""
    local = sorted((REPO / "storage" / "tasks" / task_id).glob("final-*.mp4"))
    if local:
        shutil.copy(local[0], OUT)
        return
    for url in videos:
        full = url if url.startswith("http") else f"{API}/{url.lstrip('/')}"
        r = requests.get(full, timeout=600)
        if r.ok and r.content:
            OUT.write_bytes(r.content)
            return
    raise RuntimeError("Task finished but the video file could not be found")


def generate_once(topic):
    payload = {
        "video_subject": topic,
        "video_aspect": "9:16",
        "video_source": "pexels" if env("PEXELS_API_KEY") else "pixabay",
        "voice_name": VOICE,
        "subtitle_enabled": True,
        "video_count": 1,
    }
    r = requests.post(f"{API}/api/v1/videos", json=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Create task failed: {r.status_code} {r.text[:300]}")
    task_id = r.json()["data"]["task_id"]
    print("task:", task_id)

    for _ in range(240):  # up to about 40 minutes
        time.sleep(10)
        resp = requests.get(f"{API}/api/v1/tasks/{task_id}", timeout=30)
        if not resp.ok:
            continue
        d = resp.json().get("data", {})
        print("progress:", d.get("progress"), "state:", d.get("state"))
        if d.get("state") in FAILED_STATES:
            raise RuntimeError(f"Generation failed: {d}")
        if d.get("videos"):
            fetch_video(task_id, d["videos"])
            return OUT
    raise TimeoutError("Generation timed out")


def generate(topic, attempts=2):
    last = None
    for i in range(attempts):
        try:
            return generate_once(topic)
        except Exception as e:  # retry once, for example on a transient LLM error
            last = e
            print(f"Attempt {i + 1} failed: {e}")
    raise last


# -------------------------------------------------------------- delivery ----
def telegram_ready():
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def tg_text(text):
    if not telegram_ready():
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
            data={"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[:3500]}, timeout=60)
        if not r.ok:
            print("Telegram message failed:", r.text[:300])
    except Exception as e:
        print("Telegram message error:", type(e).__name__)


def tg_video(path, caption):
    if not telegram_ready():
        print("Telegram not configured, skipping.")
        return
    if path.stat().st_size > TELEGRAM_LIMIT:
        tg_text("Your Short is ready but is over Telegram's 50 MB limit. "
                "Download it from the workflow run's Artifacts section.")
        return
    try:
        with open(path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendVideo",
                data={"chat_id": env("TELEGRAM_CHAT_ID"), "caption": caption[:900],
                      "supports_streaming": "true"},
                files={"video": f}, timeout=900)
        print("Telegram:", "sent" if r.ok else r.text[:300])
    except Exception as e:
        print("Telegram video error:", type(e).__name__)


def upload_youtube(path, title, description):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=env("YT_REFRESH_TOKEN"),
        client_id=env("YT_CLIENT_ID"),
        client_secret=env("YT_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:90] + " #Shorts", "description": description,
                    "categoryId": CATEGORY_ID},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(path), resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("Uploaded:", f"https://youtu.be/{resp['id']}")


# ------------------------------------------------------------------ main ----
def main():
    topic = env("TOPIC") or TOPICS[datetime.date.today().toordinal() % len(TOPICS)]
    print("Topic:", topic)
    try:
        setup()
        server = start_server()
        try:
            video = generate(topic)
        finally:
            server.terminate()
        tg_video(video, topic)
        if env("YT_REFRESH_TOKEN"):
            upload_youtube(video, topic, f"{topic}\n\nMade with AI.")
        print("Done:", video)
    except Exception as e:
        run_url = ""
        if os.environ.get("GITHUB_RUN_ID"):
            run_url = (f"\n{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                       f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
        tg_text(f"Daily Short failed: {e}{run_url}")
        raise


if __name__ == "__main__":
    main()
