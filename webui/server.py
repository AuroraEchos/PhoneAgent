"""Dependency-free localhost HTTP server for the PhoneAgent web console."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import socket
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from webui.runtime import ConsoleRuntime


STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 64 * 1024


class ConsoleHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], runtime: ConsoleRuntime):
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, ConsoleRequestHandler)
        self.runtime = runtime


class ConsoleRequestHandler(BaseHTTPRequestHandler):
    server: ConsoleHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(self.server.runtime.snapshot())
            return
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Invalid event cursor")
                return
            self._send_json(self.server.runtime.events_after(after))
            return
        if parsed.path == "/api/trajectories":
            self._send_json({"trajectories": self.server.runtime.trajectories.list()})
            return
        if parsed.path == "/api/trajectory":
            query = parse_qs(parsed.query)
            filename = query.get("name", [""])[0]
            try:
                if query.get("download", ["0"])[0] == "1":
                    self._send_download(self.server.runtime.trajectories.path_for(filename))
                else:
                    self._send_json(self.server.runtime.trajectories.read(filename))
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except FileNotFoundError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Trajectory not found")
            except (OSError, json.JSONDecodeError) as exc:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._same_origin_request():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Cross-origin request rejected")
            return
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/tasks":
            try:
                task = self.server.runtime.start_task(str(payload.get("task", "")))
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            except RuntimeError as exc:
                self._send_error_json(HTTPStatus.CONFLICT, str(exc))
            else:
                self._send_json({"task": task}, status=HTTPStatus.ACCEPTED)
            return

        if parsed.path == "/api/checks":
            if self.server.runtime.start_checks():
                self._send_json({"status": "checking"}, status=HTTPStatus.ACCEPTED)
            else:
                self._send_error_json(
                    HTTPStatus.CONFLICT,
                    "检查正在执行，或当前任务尚未结束",
                )
            return

        if parsed.path == "/api/prompts/respond":
            prompt_id = str(payload.get("id", ""))
            accepted = payload.get("accepted") is True
            try:
                self.server.runtime.respond_prompt(prompt_id, accepted)
            except ValueError as exc:
                self._send_error_json(HTTPStatus.CONFLICT, str(exc))
            else:
                self._send_json({"accepted": accepted})
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, "API route not found")

    def _read_json_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("Invalid request body size")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _same_origin_request(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in {f"http://{host}", f"https://{host}"}

    def _send_static(self, request_path: str) -> None:
        mapping = {
            "/": STATIC_ROOT / "index.html",
            "/index.html": STATIC_ROOT / "index.html",
            "/app.js": STATIC_ROOT / "app.js",
            "/style.css": STATIC_ROOT / "style.css",
        }
        path = mapping.get(request_path)
        if path is None or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_download(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _security_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def log_message(self, format: str, *args: Any) -> None:
        if self.path.startswith("/api/") and args and str(args[1]).startswith("2"):
            return
        super().log_message(format, *args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PhoneAgent local Web Console")
    parser.add_argument(
        "--host",
        default=os.getenv("PHONE_AGENT_WEB_HOST", "127.0.0.1"),
        help="Bind address; keep 127.0.0.1 unless you add your own authentication",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PHONE_AGENT_WEB_PORT", "8765")),
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the console in the default browser after the server starts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be in the range 1..65535")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "WARNING: this console controls an Android device and has no authentication. "
            "Binding beyond localhost is not recommended."
        )

    runtime = ConsoleRuntime(Path.cwd())
    server = ConsoleHTTPServer((args.host, args.port), runtime)
    runtime.start_checks()
    host_for_url = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url_host = f"[{host_for_url}]" if ":" in host_for_url else host_for_url
    url = f"http://{url_host}:{args.port}"
    print(f"PhoneAgent Web Console: {url}")
    print("Startup checks run once for this server session. Press Ctrl+C to stop.")
    if args.open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping PhoneAgent Web Console...")
    finally:
        runtime.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
