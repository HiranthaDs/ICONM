import json
import shutil
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Callable

from config import DB_PATH, SYNC_PASSWORD
from database import get_setting
from services import sync_password_ok

_server: Optional[ThreadingHTTPServer] = None
_thread: Optional[threading.Thread] = None


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class SyncHandler(BaseHTTPRequestHandler):
    def _auth(self) -> bool:
        token = self.headers.get("X-ICON-SYNC", "")
        return sync_password_ok(token)

    def do_GET(self):
        if self.path.startswith("/ping"):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "app": "ICON MOBILE SYSTEM"}).encode())
            return
        if self.path.startswith("/db"):
            if not self._auth():
                self.send_response(403); self.end_headers(); return
            data = DB_PATH.read_bytes() if DB_PATH.exists() else b""
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path.startswith("/db"):
            if not self._auth():
                self.send_response(403); self.end_headers(); return
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length)
            tmp = DB_PATH.with_suffix(".sync_upload_tmp")
            backup = DB_PATH.with_suffix(".before_sync_push")
            if DB_PATH.exists():
                shutil.copy2(DB_PATH, backup)
            tmp.write_bytes(data)
            shutil.move(str(tmp), str(DB_PATH))
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok": True}).encode())
            return
        self.send_response(404); self.end_headers()

    def log_message(self, format, *args):
        return


def start_server(port: int = 8787) -> str:
    global _server, _thread
    if _server:
        return f"http://{local_ip()}:{_server.server_port}"
    _server = ThreadingHTTPServer(("0.0.0.0", port), SyncHandler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return f"http://{local_ip()}:{port}"


def stop_server() -> None:
    global _server, _thread
    if _server:
        _server.shutdown(); _server.server_close()
    _server = None; _thread = None


def pull_database(host_url: str, password: str = SYNC_PASSWORD) -> None:
    url = host_url.rstrip("/") + "/db"
    req = urllib.request.Request(url, headers={"X-ICON-SYNC": password})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = r.read()
    if not data:
        raise ValueError("Host database is empty")
    tmp = DB_PATH.with_suffix(".sync_pull_tmp")
    backup = DB_PATH.with_suffix(".before_sync_pull")
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup)
    tmp.write_bytes(data)
    shutil.move(str(tmp), str(DB_PATH))


def push_database(host_url: str, password: str = SYNC_PASSWORD) -> None:
    url = host_url.rstrip("/") + "/db"
    data = DB_PATH.read_bytes()
    req = urllib.request.Request(url, data=data, method="POST", headers={"X-ICON-SYNC": password, "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=12) as r:
        r.read()
