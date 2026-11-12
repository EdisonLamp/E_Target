"""MicroPython access point and web server for the E-Target interface.

Copy this file, index.html, font.css and icon.png to the Pico 2 W filesystem,
then run pico_server.py. Connect to the configured Wi-Fi and open the printed
address. Call send_shot(x, y) from the measurement code to add a shot.
"""

import math
import os
import select
import socket
import time

try:
    import ujson as json
except ImportError:
    import json

import network


WIFI_SSID = "E-Target"
SERVER_IP = "192.168.4.1"
PORT = 80
DNS_PORT = 53
MAX_REQUEST_SIZE = 4096
MAX_HEADER_SIZE = 8192
MAX_SHOTS = 10
TARGET_TYPE = 10
EVENT_HEARTBEAT_MS = 15000
BASE_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."

_shots = []
_revision = 0
_max_shots = MAX_SHOTS
_target_type = TARGET_TYPE


def _validate_position(x, y):
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        raise ValueError("x und y muessen Zahlen zwischen 0 und 800 sein")
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 800 and 0 <= y <= 800):
        raise ValueError("x und y muessen zwischen 0 und 800 liegen")
    return x, y


def send_shot(x, y):
    """Add target coordinates in the interface's 0..800 coordinate space."""
    global _revision

    x, y = _validate_position(x, y)
    if len(_shots) >= _max_shots:
        raise RuntimeError("Maximale Schusszahl erreicht")
    _shots.append({"x": x, "y": y})
    _revision += 1


def _state():
    return {
        "revision": _revision,
        "maxShots": _max_shots,
        "targetType": _target_type,
        "shots": list(_shots),
    }


def _response(status, body=b"", content_type="text/plain; charset=utf-8", extra_headers=""):
    reasons = {
        200: "OK",
        204: "No Content",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        413: "Payload Too Large",
        500: "Internal Server Error",
    }
    if isinstance(body, str):
        body = body.encode()
    header = (
        "HTTP/1.1 {} {}\r\n"
        "Content-Type: {}\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "{}\r\n"
    ).format(status, reasons.get(status, "Error"), content_type, len(body), extra_headers)
    return header.encode() + body


def _json_body(body):
    try:
        return json.loads(body.decode())
    except (ValueError, UnicodeError):
        raise ValueError("Ungueltiges JSON")


def _handle_request(request):
    global _revision, _max_shots, _target_type

    method, path, headers, body = request
    path = path.split("?", 1)[0]

    if method == "GET" and path == "/events":
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream; charset=utf-8\r\n"
            b"Cache-Control: no-cache\r\n"
            b"Connection: keep-alive\r\n\r\n"
        )
        return {"mode": "sse", "pending": response, "revision": -1, "last_event": time.ticks_ms()}

    if method == "GET":
        filenames = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/font.css": ("font.css", "text/css; charset=utf-8"),
            "/icon.png": ("icon.png", "image/png"),
        }
        asset = filenames.get(path, filenames["/"])
        filename, content_type = asset
        filepath = (BASE_DIR + "/" + filename) if BASE_DIR != "." else filename
        try:
            file_handle = open(filepath, "rb")
            length = os.stat(filepath)[6]
        except OSError:
            return {"mode": "write", "pending": _response(404, "Datei nicht gefunden")}
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: {}\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(content_type, length).encode()
        return {"mode": "file", "pending": header, "file": file_handle}

    if method != "POST":
        return {"mode": "write", "pending": _response(405, "Methode nicht erlaubt")}

    if path == "/reset":
        _shots.clear()
        _revision += 1
        return {"mode": "write", "pending": _response(204)}

    if path not in ("/shot", "/settings"):
        return {"mode": "write", "pending": _response(404, "Datei nicht gefunden")}

    try:
        data = _json_body(body)
        if not isinstance(data, dict):
            raise ValueError("JSON-Objekt erwartet")

        if path == "/settings":
            max_shots = data["maxShots"]
            target_type = data.get("targetType", _target_type)
            if type(max_shots) is not int or not 1 <= max_shots <= 100:
                raise ValueError("Ungueltige Schusszahl")
            if type(target_type) is not int or target_type not in (10, 15):
                raise ValueError("Ungueltiger Zieltyp")
            _max_shots = max_shots
            _target_type = target_type
            del _shots[:-max_shots]
            _revision += 1
            return {"mode": "write", "pending": _response(204)}

        try:
            x, y = _validate_position(data["x"], data["y"])
        except KeyError:
            raise ValueError("x und y fehlen")
        if len(_shots) >= _max_shots:
            return {"mode": "write", "pending": _response(409, "Maximale Schusszahl erreicht")}
        _shots.append({"x": x, "y": y})
        _revision += 1
        return {"mode": "write", "pending": _response(204)}
    except (KeyError, TypeError, ValueError):
        message = "Ungueltige Einstellungen" if path == "/settings" else "x und y muessen zwischen 0 und 800 liegen"
        return {"mode": "write", "pending": _response(400, message)}


def _parse_request(buffer):
    separator = buffer.find(b"\r\n\r\n")
    if separator < 0:
        if len(buffer) > MAX_HEADER_SIZE:
            return "error", _response(413, "Anfrage zu gross")
        return None, None

    try:
        lines = bytes(buffer[:separator]).decode().split("\r\n")
        method, path, _version = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        content_length = int(headers.get("content-length", "0"))
        if content_length < 0:
            raise ValueError
    except (UnicodeError, ValueError):
        return "error", _response(400, "Ungueltiger HTTP-Header")

    if content_length > MAX_REQUEST_SIZE:
        return "error", _response(413, "Anfrage zu gross")
    body_start = separator + 4
    if len(buffer) - body_start < content_length:
        return None, None
    body = bytes(buffer[body_start:body_start + content_length])
    return "request", (method, path, headers, body)


def _dns_response(packet):
    if len(packet) < 17 or packet[4:6] != b"\x00\x01":
        return None

    cursor = 12
    while cursor < len(packet):
        label_length = packet[cursor]
        cursor += 1
        if label_length == 0:
            break
        if label_length > 63 or cursor + label_length > len(packet):
            return None
        cursor += label_length
    else:
        return None

    question_end = cursor + 4
    if question_end > len(packet):
        return None

    question_type = packet[cursor] << 8 | packet[cursor + 1]
    question_class = packet[cursor + 2] << 8 | packet[cursor + 3]
    answers = 1 if question_type == 1 and question_class == 1 else 0
    flags = 0x8400 | (packet[2] & 0x01)
    header = packet[:2] + bytes((flags >> 8, flags & 0xFF, 0, 1, 0, answers, 0, 0, 0, 0))
    response = header + packet[12:question_end]
    if answers:
        address = bytes(int(part) for part in SERVER_IP.split("."))
        response += b"\xC0\x0C\x00\x01\x00\x01\x00\x00\x00\x3C\x00\x04" + address
    return response


def _register(poller, client, events):
    try:
        poller.modify(client, events)
    except OSError:
        poller.register(client, events)


def _close_client(poller, clients, client):
    state = clients.pop(client, None)
    if state is None:
        return
    try:
        poller.unregister(client)
    except OSError:
        pass
    if "file" in state:
        state["file"].close()
    client.close()


def _queue_sse(state):
    payload = "data: {}\n\n".format(json.dumps(_state())).encode()
    state["pending"] = payload
    state["offset"] = 0
    state["revision"] = _revision
    state["last_event"] = time.ticks_ms()


def serve_forever():
    """Start the Wi-Fi access point and serve the interface on port 80."""
    ap = network.WLAN(network.AP_IF)
    ap.config(ssid=WIFI_SSID)
    ap.active(True)
    while not ap.active():
        time.sleep_ms(100)

    dns_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dns_server.bind(("0.0.0.0", DNS_PORT))
    dns_server.setblocking(False)

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(4)
    server.setblocking(False)

    poller = select.poll()
    poller.register(server, select.POLLIN)
    poller.register(dns_server, select.POLLIN)
    clients = {}
    print("WLAN: {}".format(WIFI_SSID))
    print("Oeffne http://{}/".format(SERVER_IP))

    while True:
        for client, event in poller.poll(1000):
            if client is dns_server:
                try:
                    query, address = dns_server.recvfrom(512)
                    response = _dns_response(query)
                    if response is not None:
                        dns_server.sendto(response, address)
                except OSError:
                    pass
                continue

            if client is server:
                try:
                    connection, _address = server.accept()
                    connection.setblocking(False)
                    clients[connection] = {"mode": "read", "buffer": bytearray()}
                    poller.register(connection, select.POLLIN)
                except OSError:
                    pass
                continue

            state = clients.get(client)
            if state is None:
                continue
            if event & (select.POLLERR | select.POLLHUP):
                _close_client(poller, clients, client)
                continue
            if event & select.POLLIN:
                try:
                    received = client.recv(1024)
                except OSError:
                    _close_client(poller, clients, client)
                    continue
                if not received:
                    _close_client(poller, clients, client)
                    continue
                if state["mode"] == "sse":
                    _close_client(poller, clients, client)
                    continue
                state["buffer"].extend(received)
                parsed, request = _parse_request(state["buffer"])
                if parsed == "error":
                    state.update({"mode": "write", "pending": request, "offset": 0})
                    _register(poller, client, select.POLLOUT)
                elif parsed == "request":
                    response = _handle_request(request)
                    state.update(response)
                    state.setdefault("offset", 0)
                    if state["mode"] == "sse":
                        _register(poller, client, select.POLLIN | select.POLLOUT)
                    else:
                        _register(poller, client, select.POLLOUT)

            if event & select.POLLOUT and client in clients:
                state = clients[client]
                try:
                    if state["pending"]:
                        sent = client.send(state["pending"][state.get("offset", 0):])
                        state["offset"] = state.get("offset", 0) + sent
                    if state["offset"] >= len(state["pending"]):
                        state["pending"] = b""
                        state["offset"] = 0
                        if state["mode"] == "write":
                            _close_client(poller, clients, client)
                            continue
                        if state["mode"] == "file":
                            chunk = state["file"].read(1024)
                            if chunk:
                                state["pending"] = chunk
                            else:
                                _close_client(poller, clients, client)
                                continue
                        if state["mode"] == "sse":
                            _register(poller, client, select.POLLIN)
                except OSError:
                    _close_client(poller, clients, client)

        now = time.ticks_ms()
        for client, state in tuple(clients.items()):
            if state["mode"] != "sse" or state["pending"]:
                continue
            if state["revision"] != _revision:
                _queue_sse(state)
                _register(poller, client, select.POLLIN | select.POLLOUT)
            elif time.ticks_diff(now, state["last_event"]) >= EVENT_HEARTBEAT_MS:
                state["pending"] = b": keep-alive\n\n"
                state["offset"] = 0
                state["last_event"] = now
                _register(poller, client, select.POLLIN | select.POLLOUT)


if __name__ == "__main__":
    serve_forever()
