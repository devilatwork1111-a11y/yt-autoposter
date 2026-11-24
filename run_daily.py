"""Daily pipeline: MoneyPrinterTurbo -> generate a Short -> upload to YouTube.
Works in Google Colab (secrets from the Secrets panel) and in GitHub Actions (env vars).
"""
import datetime, os, pathlib, re, subprocess, sys, time
import requests

REPO = pathlib.Path("MoneyPrinterTurbo")
API = "http://127.0.0.1:8080"

# ---- EDIT THESE -------------------------------------------------------------
TOPICS = [
    "3 surprising facts about the human brain",
    "Why the ocean is salty",
    "How black holes are formed",
    "Habits of highly productive people",
    "The history of the internet in 60 seconds",
]
PRIVACY = "private"          # change to "public" once you've reviewed output quality
CATEGORY_ID = "27"           # 27 = Education
VOICE = "en-US-AriaNeural-Female"
# -----------------------------------------------------------------------------


def env(key, default=""):
    try:
        from google.colab import userdata
        return userdata.get(key)
    except Exception:
        return os.environ.get(key, default)


def setup():
    if not REPO.exists():
        subprocess.run(["git", "clone", "https://github.com/harry0703/MoneyPrinterTurbo.git"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(REPO / "requirements.txt")], check=True)
    cfg = (REPO / "config.example.toml").read_text()

    def setk(txt, key, val):
        return re.sub(rf"^{key}\s*=.*$", f"{key} = {val}", txt, flags=re.M)

    cfg = setk(cfg, "llm_provider", f'"{env("LLM_PROVIDER", "openai")}"')
    cfg = setk(cfg, "openai_api_key", f'"{env("OPENAI_API_KEY")}"')
    cfg = setk(cfg, "pexels_api_keys", f'["{env("PEXELS_API_KEY")}"]')
    (REPO / "config.toml").write_text(cfg)


def start_server():
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=REPO)
    for _ in range(60):
        try:
            requests.get(f"{API}/docs", timeout=2)
            return proc
        except Exception:
            time.sleep(2)
    raise RuntimeError("MoneyPrinterTurbo API did not start")


def generate(topic):
    payload = {
        "video_subject": topic,
        "video_aspect": "9:16",
        "voice_name": VOICE,
        "video_language": "",
        "subtitle_enabled": True,
        "video_count": 1,
    }
    r = requests.post(f"{API}/api/v1/videos", json=payload, timeout=60)
    r.raise_for_status()
    task_id = r.json()["data"]["task_id"]
    print("task:", task_id)
    for _ in range(180):  # up to ~30 min
        time.sleep(10)
        d = requests.get(f"{API}/api/v1/tasks/{task_id}", timeout=30).json()["data"]
        print("progress:", d.get("progress"), "state:", d.get("state"))
        if d.get("state") == 1:
            url = d["videos"][0]
            out = pathlib.Path("final.mp4")
            if url.startswith("http"):
                out.write_bytes(requests.get(url, timeout=300).content)
            else:
                out.write_bytes(pathlib.Path(url).read_bytes())
            return out
        if d.get("state") == -1:
            raise RuntimeError(f"Generation failed: {d}")
    raise TimeoutError("Generation timed out")


def upload(path, title, description):
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
        "snippet": {"title": title[:95] + " #Shorts", "description": description, "categoryId": CATEGORY_ID},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(path), resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("Uploaded:", f"https://youtu.be/{resp['id']}")


if __name__ == "__main__":
    topic = TOPICS[datetime.date.today().toordinal() % len(TOPICS)]
    setup()
    server = start_server()
    try:
        video = generate(topic)
        if env("YT_REFRESH_TOKEN"):
            upload(video, topic, f"{topic}\n\nMade with AI.")
        else:
            print("No YT_REFRESH_TOKEN set, skipping upload. Video saved as", video)
    finally:
        server.terminate()
