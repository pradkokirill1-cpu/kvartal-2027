"""Static catalog plus one read-only endpoint, with stale-while-revalidate."""
import hashlib
import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from catalog import CACHE, CURATED, ROOT, SNAPSHOT, refresh, seed

TTL = 24 * 60 * 60
guard = threading.Lock()
published = seed()
version = hashlib.sha256(SNAPSHOT.read_bytes() + CURATED.read_bytes()).hexdigest()
last_attempt = 0
loading = False

try:
    saved = json.loads(CACHE.read_text(encoding="utf-8"))
    if saved["version"] == version and isinstance(saved["data"]["rows"], list):
        published, last_attempt = saved["data"], saved["time"]
except (OSError, ValueError, KeyError, TypeError):
    pass


def job(previous):
    global published, loading
    try:
        updated = refresh(previous)
        with guard:
            published = updated
        try:
            temp = CACHE.with_name(".catalog-cache.tmp")
            temp.write_text(json.dumps({"data": updated, "time": last_attempt, "version": version}, ensure_ascii=False), encoding="utf-8")
            temp.replace(CACHE)
        except OSError:
            pass
    except Exception as exc:
        print(f"Refresh failed: {type(exc).__name__}: {exc}", flush=True)
    finally:
        with guard:
            loading = False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "public"), **kwargs)

    def do_GET(self):
        global last_attempt, loading
        if urlsplit(self.path).path not in ("/api/catalog", "/port/5000/api/catalog"):
            return super().do_GET()
        with guard:
            if not loading and time.time() - last_attempt >= TTL:
                last_attempt = time.time()
                loading = True
                threading.Thread(target=job, args=(published,), daemon=True).start()
            payload = json.dumps(dict(published, refreshing=loading), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def list_directory(self, _path):
        self.send_error(404)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "5000"))), Handler).serve_forever()
