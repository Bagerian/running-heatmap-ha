"""Static file server for the heatmap viewer + admin UI."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import struct
import subprocess
import sys
import threading
import zlib
from functools import partial
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import BinaryIO


# ── Transparent 1×1 PNG ─────────────────────────────────────────────────────

def _make_transparent_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (sig
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
            + chunk(b"IEND", b""))

_TRANSPARENT_PNG = _make_transparent_png()
_ADMIN_HTML = Path(__file__).resolve().parent / "admin.html"


# ── Config builder ───────────────────────────────────────────────────────────
# Build config purely from environment variables set by run.sh.
# We never import main_ha.py (which would re-run the generator).

def _build_config():
    """Build a Config object from env vars written by run.sh."""
    from heatmap.config import ActivityType, Config
    strava_dir     = os.environ.get("HEATMAP_STRAVA_DIR", "/share/running_heatmap/strava_export")
    icu_cache_dir  = os.environ.get("HEATMAP_ICU_CACHE_DIR", "/share/running_heatmap/cache/intervals_icu")
    return Config(
        activities_dir=strava_dir,
        intervals_icu_cache_dir=icu_cache_dir,
        activity_type_profiles={
            "runs":       [ActivityType.RUN],
            "trail_runs": [ActivityType.TRAIL_RUN],
            "hikes":      [ActivityType.HIKE],
            "all":        [ActivityType.RUN, ActivityType.TRAIL_RUN, ActivityType.HIKE],
        },
    )


# ── Regeneration ─────────────────────────────────────────────────────────────

_regen_lock = threading.Lock()
_regen_status: dict = {"running": False, "last": None, "message": ""}

def _run_regenerate() -> None:
    global _regen_status
    main_py = os.environ.get("HEATMAP_MAIN_PY", "/app/main_ha.py")
    env = os.environ.copy()
    # HEATMAP_SKIP_SYNC=1  → skips intervals.icu download but still re-parses all tracks (slow)
    # HEATMAP_HTML_ONLY=1  → skips everything, just re-renders HTML from existing tile metadata (fast)
    # We want a full tile rebuild from cache, so skip sync only
    env["HEATMAP_SKIP_SYNC"] = "1"
    env["HEATMAP_YES"] = "1"
    try:
        result = subprocess.run(
            ["uv", "run", "python", main_py],
            capture_output=True, text=True, cwd="/app", env=env,
            timeout=1800,  # 30 min max
        )
        if result.returncode == 0:
            _regen_status = {"running": False, "last": "ok",
                             "message": "Heatmap regenerated successfully."}
        else:
            err = (result.stderr or result.stdout or "unknown error")[-800:]
            _regen_status = {"running": False, "last": "error", "message": err}
    except subprocess.TimeoutExpired:
        _regen_status = {"running": False, "last": "error",
                         "message": "Timed out after 30 minutes."}
    except Exception as exc:
        _regen_status = {"running": False, "last": "error", "message": str(exc)}


# ── HTTP handler ─────────────────────────────────────────────────────────────

class HeatmapHandler(SimpleHTTPRequestHandler):

    def _ingress_path(self) -> str:
        return self.headers.get("X-Ingress-Path", "").strip() or "/"

    def _plain_path(self) -> str:
        ingress = self._ingress_path().rstrip("/")
        p = self.path.split("?")[0]
        if ingress and ingress != "/" and p.startswith(ingress):
            p = p[len(ingress):] or "/"
        return p

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _inject_base(self, html: bytes, base: str) -> bytes:
        tag = f'<base href="{base.rstrip("/")}/">'.encode()
        if b"<head>" in html:
            return html.replace(b"<head>", b"<head>" + tag, 1)
        return tag + html

    # ── GET ──────────────────────────────────────────────────────────────────

    def send_head(self) -> BytesIO | BinaryIO | None:
        plain = self._plain_path()

        if plain in ("/", "/index.html"):
            self.path = "/heatmap.html"
            return super().send_head()

        if plain in ("/admin", "/admin/", "/admin/index.html"):
            if not _ADMIN_HTML.exists():
                self.send_error(500, "admin.html missing"); return None
            html = _ADMIN_HTML.read_bytes()
            ingress = self._ingress_path()
            if ingress and ingress != "/":
                html = self._inject_base(html, ingress.rstrip("/") + "/admin/")
            self._send_html(html)
            return None

        if plain.startswith("/tiles/") and plain.endswith(".png"):
            self.path = plain
            if not Path(self.translate_path(plain)).is_file():
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(_TRANSPARENT_PNG)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                return BytesIO(_TRANSPARENT_PNG)

        self.path = plain
        return super().send_head()

    def do_GET(self) -> None:  # noqa: N802
        plain = self._plain_path()

        if plain == "/admin/api/activities":
            try:
                config = _build_config()
                from heatmap.admin import list_activities
                self._send_json(list_activities(config))
            except Exception as exc:
                import traceback
                self._send_json({"error": str(exc), "traceback": traceback.format_exc()}, status=500)
            return

        if plain == "/admin/api/regen-status":
            self._send_json(_regen_status)
            return

        if plain == "/admin/api/debug":
            import traceback as tb
            info = {
                "HEATMAP_STRAVA_DIR":    os.environ.get("HEATMAP_STRAVA_DIR", "NOT SET"),
                "HEATMAP_ICU_CACHE_DIR": os.environ.get("HEATMAP_ICU_CACHE_DIR", "NOT SET"),
                "HEATMAP_CACHE_DIR":     os.environ.get("HEATMAP_CACHE_DIR", "NOT SET"),
                "HEATMAP_OUTPUT_DIR":    os.environ.get("HEATMAP_OUTPUT_DIR", "NOT SET"),
                "HEATMAP_MAIN_PY":       os.environ.get("HEATMAP_MAIN_PY", "NOT SET"),
                "self.path":             self.path,
                "plain_path":            plain,
                "X-Ingress-Path":        self.headers.get("X-Ingress-Path", "NOT SET"),
            }
            # Test config build
            try:
                config = _build_config()
                info["config_ok"] = True
                info["strava_dir_exists"]     = str(Path(config.resolved_activities_dir()).exists())
                info["icu_cache_dir_exists"]  = str(Path(config.resolved_intervals_icu_cache_dir()).exists())
                info["index_json_exists"]     = str((Path(config.resolved_intervals_icu_cache_dir()) / "index.json").exists())
            except Exception as exc:
                info["config_ok"] = False
                info["config_error"] = str(exc)
                info["config_traceback"] = tb.format_exc()
            self._send_json(info)
            return

        super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self) -> None:  # noqa: N802
        global _regen_status
        plain = self._plain_path()

        if plain == "/admin/api/upload-strava":
            import zipfile
            import io
            import shutil
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)

                # In a real multipart form, we'd have to parse it.
                # For simplicity, if we just POST the raw zip file as the body from JS, we can parse it directly.
                # But HTML file inputs usually send multipart. Let's do a basic parse or expect raw binary.

                # Wait, if we use JS fetch, we can send the raw file as the body.

                strava_dir = os.environ.get("HEATMAP_STRAVA_DIR", "/share/running_heatmap/strava_export")
                strava_path = Path(strava_dir)
                strava_path.mkdir(parents=True, exist_ok=True)

                # Try to read as ZIP
                try:
                    with zipfile.ZipFile(io.BytesIO(body)) as z:
                        z.extractall(strava_path)
                    self._send_json({"ok": True, "message": "Extracted ZIP successfully."})
                except zipfile.BadZipFile:
                    # Maybe it's just the activities.csv?
                    # Let's check if it starts with the CSV header
                    if b"Activity ID,Activity Date" in body:
                        (strava_path / "activities.csv").write_bytes(body)
                        self._send_json({"ok": True, "message": "Saved activities.csv successfully."})
                    else:
                        self._send_json({"ok": False, "error": "Not a valid Strava export ZIP or activities.csv"}, status=400)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if plain == "/admin/api/exclude":
            try:
                data = self._read_json()
                source   = data.get("source")
                ids      = data.get("ids") or []
                excluded = bool(data.get("excluded"))
                if source not in ("strava", "intervals") or not isinstance(ids, list):
                    self._send_json({"ok": False, "error": "bad payload"}, status=400); return
                config = _build_config()
                from heatmap.admin import set_excluded
                overrides = set_excluded(config, source, [str(i) for i in ids], excluded)
                self._send_json({"ok": True, "overrides": overrides})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if plain == "/admin/api/sync":
            try:
                config = _build_config()
                from heatmap.admin import sync_all_intervals
                self._send_json(sync_all_intervals(config))
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if plain == "/admin/api/reimport":
            try:
                data = self._read_json()
                aid = data.get("id")
                if not aid:
                    self._send_json({"ok": False, "error": "missing id"}, status=400); return
                config = _build_config()
                from heatmap.admin import reimport_intervals
                self._send_json(reimport_intervals(config, str(aid)))
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if plain == "/admin/api/regenerate":
            with _regen_lock:
                if _regen_status.get("running"):
                    self._send_json({"ok": False, "error": "Already running"}); return
                _regen_status = {"running": True, "last": None, "message": "Regenerating…"}
            threading.Thread(target=_run_regenerate, daemon=True).start()
            self._send_json({"ok": True, "message": "Regeneration started."})
            return

        if plain == "/admin/api/clear-cache":
            try:
                import shutil
                icu_cache = os.environ.get("HEATMAP_ICU_CACHE_DIR",
                                           "/share/running_heatmap/cache/intervals_icu")
                cache_dir = Path(icu_cache)
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                cache_dir.mkdir(parents=True, exist_ok=True)
                # Also remove the track cache so stale entries don't linger
                track_cache = Path(os.environ.get("HEATMAP_CACHE_DIR",
                                                   "/share/running_heatmap/cache")) / "track_cache.json"
                track_cache.unlink(missing_ok=True)
                self._send_json({"ok": True})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        self.send_error(404)

    def handle(self) -> None:
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            super().handle()

    def log_message(self, fmt, *args) -> None:
        try:
            status = int(args[1])
        except (IndexError, ValueError, TypeError):
            status = 0
        if 400 <= status < 600:
            return
        super().log_message(fmt, *args)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--directory", default="outputs")
    args = parser.parse_args()

    handler = partial(HeatmapHandler, directory=args.directory)
    server  = ThreadingHTTPServer(("", args.port), handler)
    print(f"Serving {args.directory}/ on port {args.port}", file=sys.stderr)
    print(f"  Heatmap : http://localhost:{args.port}/heatmap.html", file=sys.stderr)
    print(f"  Admin   : http://localhost:{args.port}/admin", file=sys.stderr)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
