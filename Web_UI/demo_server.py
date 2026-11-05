"""Serve the target and accept live positions with send_shot(x, y)."""

import json
import math
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition
from urllib.request import Request, urlopen


URL = "http://127.0.0.1:8000"
WEB_ROOT = Path(__file__).resolve().parent


def send_shot(x, y):
    """Send target coordinates in the SVG's 0..800 coordinate space."""
    data = json.dumps({"x": x, "y": y}).encode()
    request = Request(f"{URL}/shot", data=data, headers={"Content-Type": "application/json"})
    urlopen(request, timeout=1).close()


class Handler(SimpleHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, format, *args):
        if self.path != "/events":
            super().log_message(format, *args)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 4096:
            raise ValueError("Ungueltige Anfrage")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last_revision = -1
            try:
                while True:
                    with self.server.state_changed:
                        changed = self.server.state_changed.wait_for(
                            lambda: self.server.revision != last_revision,
                            timeout=15,
                        )
                        state = {
                            "revision": self.server.revision,
                            "maxShots": self.server.max_shots,
                            "targetType": self.server.target_type,
                            "shots": list(self.server.shots),
                        }
                    if not changed:
                        self.wfile.write(b": keep-alive\n\n")
                    else:
                        data = json.dumps(state).encode()
                        self.wfile.write(b"data: " + data + b"\n\n")
                        last_revision = state["revision"]
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        super().do_GET()

    def do_POST(self):
        if self.path == "/reset":
            with self.server.state_changed:
                self.server.shots.clear()
                self.server.revision += 1
                self.server.state_changed.notify_all()
            self.send_response(204)
            self.end_headers()
            return

        if self.path == "/settings":
            try:
                settings = self.read_json()
                max_shots = settings["maxShots"]
                if isinstance(max_shots, bool) or not isinstance(max_shots, int) or not 1 <= max_shots <= 100:
                    raise ValueError
                target_type = settings.get("targetType", self.server.target_type)
                if isinstance(target_type, bool) or not isinstance(target_type, int) or target_type not in (10, 15):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400, "Ungueltige Einstellungen")
                return
            with self.server.state_changed:
                self.server.max_shots = max_shots
                self.server.target_type = target_type
                self.server.shots[:] = self.server.shots[-max_shots:]
                self.server.revision += 1
                self.server.state_changed.notify_all()
            self.send_response(204)
            self.end_headers()
            return

        if self.path != "/shot":
            self.send_error(404)
            return
        try:
            shot = self.read_json()
            x, y = float(shot["x"]), float(shot["y"])
            if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 800 and 0 <= y <= 800):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.send_error(400, "x und y muessen zwischen 0 und 800 liegen")
            return

        with self.server.state_changed:
            if len(self.server.shots) >= self.server.max_shots:
                self.send_error(409, "Maximale Schusszahl erreicht")
                return
            self.server.shots.append({"x": x, "y": y})
            self.server.revision += 1
            self.server.state_changed.notify_all()
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), partial(Handler, directory=str(WEB_ROOT)))
    server.protocol_version = "HTTP/1.1"
    server.daemon_threads = True
    server.shots = []
    server.max_shots = 10
    server.target_type = 10
    server.revision = 0
    server.state_changed = Condition()
    print(f"Zielscheibe auf diesem PC: {URL}")
    print("Zugriff im LAN: http://<IP-Adresse dieses PCs>:8000  |  Zum Beenden Strg+C")
    webbrowser.open(URL)
    server.serve_forever()
