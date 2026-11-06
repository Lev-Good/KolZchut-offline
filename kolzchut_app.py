#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KolZchut Offline Web App & Live Sync Server.
Runs a lightweight local web server (http://localhost:8000) that serves
the offline KolZchut archive and allows one-click Delta updates directly
from the browser with a live progress stream (SSE).
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

PORT = 8000
BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "kolzchut_out"

# Global state for sync progress
sync_state = {
    "running": False,
    "status": "idle",
    "message": "המערכת מוכנה",
    "progress": 0,
    "total": 0,
    "current_page": "",
    "log": []
}
sync_lock = threading.Lock()


def run_sync_worker():
    global sync_state
    with sync_lock:
        sync_state["running"] = True
        sync_state["status"] = "running"
        sync_state["message"] = "מתחבר לכל זכות ובודק שינויים..."
        sync_state["progress"] = 0
        sync_state["total"] = 0
        sync_state["current_page"] = ""
        sync_state["log"] = ["התחלת תהליך סנכרון..."]

    try:
        cmd = [sys.executable, str(BASE_DIR / "kolzchut_sync_delta.py")]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(BASE_DIR),
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            with sync_lock:
                sync_state["log"].append(line)
                if len(sync_state["log"]) > 100:
                    sync_state["log"].pop(0)

                # Parse interesting status indicators
                if "pages listed in sitemap" in line:
                    sync_state["message"] = line
                elif "Diff vs archive index:" in line:
                    sync_state["message"] = "חושבו שינויים מול האתר המקומי"
                elif line.startswith("   fetch ["):
                    # e.g. fetch [1/12] Title
                    sync_state["current_page"] = line
                    sync_state["message"] = line
                elif "Build portal" in line:
                    sync_state["message"] = "מעדכן את פורטל החיפוש המקומי..."

        process.wait()

        # Re-build portal after sync
        with sync_lock:
            sync_state["message"] = "מעדכן את פורטל החיפוש..."
        try:
            subprocess.run(
                [sys.executable, str(BASE_DIR / "kolzchut_build_portal.py")],
                cwd=str(BASE_DIR),
                check=True
            )
        except Exception:
            pass

        with sync_lock:
            sync_state["running"] = False
            sync_state["status"] = "success" if process.returncode == 0 else "error"
            sync_state["message"] = "הסנכרון הושלם בהצלחה!" if process.returncode == 0 else f"הסנכרון הסתיים עם קוד {process.returncode}"
            sync_state["log"].append("סיום סנכרון.")
    except Exception as e:
        with sync_lock:
            sync_state["running"] = False
            sync_state["status"] = "error"
            sync_state["message"] = f"שגיאה בהרצה: {e}"
            sync_state["log"].append(f"שגיאה: {e}")


class KolZchutHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUT_DIR), **kwargs)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/api/sync-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with sync_lock:
                data = json.dumps(sync_state, ensure_ascii=False)
            self.wfile.write(data.encode("utf-8"))
            return

        elif url.path == "/api/start-sync":
            global sync_state
            with sync_lock:
                if sync_state["running"]:
                    resp = {"status": "already_running", "message": "סנכרון כבר רץ ברקע"}
                else:
                    threading.Thread(target=run_sync_worker, daemon=True).start()
                    resp = {"status": "started", "message": "סנכרון הופעל"}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            return

        super().do_GET()


def main():
    if not OUT_DIR.exists():
        print(f"Error: {OUT_DIR} does not exist.")
        sys.exit(1)

    server_address = ("127.0.0.1", PORT)
    try:
        httpd = http.server.ThreadingHTTPServer(server_address, KolZchutHTTPHandler)
    except OSError:
        # Fallback to alternate port if 8000 is occupied
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT + 1), KolZchutHTTPHandler)

    active_port = httpd.server_port
    url = f"http://localhost:{active_port}"
    print("=" * 60)
    print(f"  כל-זכות אופליין פועל כעת!")
    print(f"  כתובת: {url}")
    print("=" * 60)
    print("  לסגירה: סגור חלון זה (או לחץ Ctrl+C)")

    # Open browser automatically after 1 second
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nשרת כל-זכות כובה.")


if __name__ == "__main__":
    main()
