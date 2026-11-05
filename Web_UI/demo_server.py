"""Serve the target and accept live positions with send_shot(x, y)."""

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.request import Request, urlopen


URL = "http://127.0.0.1:8000"
WEB_ROOT = Path(__file__).resolve().parent


def send_shot(x, y):
    """Send target coordinates in the SVG's 0..800 coordinate space."""
    data = json.dumps({"x": x, "y": y}).encode()
    request = Request(f"{URL}/shot", data=data, headers={"Content-Type": "application/json"})
    urlopen(request, timeout=1).close()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        if self.path != "/position":
            super().log_message(format, *args)

    def do_GET(self):
        if self.path == "/position":
            with self.server.position_lock:
                data = json.dumps(self.server.position).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/shot":
            self.send_error(404)
            return
        try:
            length = int(self.headers["Content-Length"])
            shot = json.loads(self.rfile.read(length))
            x, y = float(shot["x"]), float(shot["y"])
            if not (0 <= x <= 800 and 0 <= y <= 800):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.send_error(400, "x und y muessen zwischen 0 und 800 liegen")
            return

        with self.server.position_lock:
            self.server.position = {"id": self.server.position["id"] + 1, "x": x, "y": y}
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), partial(Handler, directory=str(WEB_ROOT)))
    server.position = {"id": 0, "x": 400, "y": 400}
    server.position_lock = Lock()
    print(f"Zielscheibe: {URL}  |  Zum Beenden Strg+C")
    webbrowser.open(URL)
    server.serve_forever()
