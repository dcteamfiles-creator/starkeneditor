"""
Stärkenkompass Content App — Server.

Architektur (nach Pivot zu Canva Bulk Create):
  - Editor sammelt SX-Daten (alle Variablen, Schirmherren, Sponsor, QR)
  - "In Bulk-Queue legen" speichert in data/bulk_queue.json
  - "/bulk-queue" zeigt alle wartenden SX
  - "Export für Canva" liefert CSV (eine Zeile pro SX) + Bild-URLs
  - User lädt CSV in Canva Bulk Create → produziert pixel-perfekte PDFs
  - Audit-Log markiert exportierte Einträge

Stdlib-only (keine Flask/Pip-Dependencies). Lokal lauffähig:
  python3 server_stdlib.py
"""
from __future__ import annotations

import cgi
import csv
import hmac
import io
import json
import mimetypes
import os
import secrets
import sys
import time
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PUBLIC = ROOT / "public"
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
BULK_QUEUE_FILE = DATA / "bulk_queue.json"
RECORDS_FILE = DATA / "records.json"
DEFAULTS_FILE = DATA / "defaults.json"
SPONSORS_FILE = DATA / "sponsors.json"
QR_POOL_FILE = DATA / "qr_pool.json"

UPLOADS.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

ACCOUNTS = {f"Content{i}": f"ToHa{i:02d}" for i in range(1, 10)}
SECRET = os.environ.get("SX_SECRET", "dev-secret-change-in-production")
PUBLIC_BASE_URL = os.environ.get("SX_PUBLIC_URL", "http://localhost:8000")
# Load .env if present
def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

# Re-read SECRET after .env loaded (für stable signed cookies über Redeploys)
SECRET = os.environ.get("SX_SECRET", SECRET)

# Sessions als HMAC-signed cookies (kein Server-State, überlebt jeden Redeploy/Cold-Start)
SESSION_TTL_SECS = 30 * 24 * 3600   # 30 Tage


# ─── HELPERS ──────────────────────────────────────────────────────────────
def _sign(data: str) -> str:
    return hmac.new(SECRET.encode(), data.encode(), "sha256").hexdigest()[:32]


def make_session(user: str) -> str:
    """Signed cookie value: 'user|expiry|signature'."""
    expiry = int(time.time()) + SESSION_TTL_SECS
    payload = f"{user}|{expiry}"
    return f"{payload}|{_sign(payload)}"


def get_session(cookie_header):
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    sid = cookie.get("sxid")
    if not sid:
        return None
    parts = sid.value.split("|")
    if len(parts) != 3:
        return None
    user, expiry_str, sig = parts
    try:
        if int(expiry_str) < time.time():
            return None
        if not hmac.compare_digest(sig, _sign(f"{user}|{expiry_str}")):
            return None
        if user not in ACCOUNTS:
            return None
        return {"user": user}
    except Exception:
        return None


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ─── CSV EXPORT FOR CANVA ─────────────────────────────────────────────────
# Sponsor & Schirmherren werden in Canva manuell ergänzt → nicht im CSV.
CANVA_CSV_COLUMNS = [
    "person_name",
    "header",
    "pruefnummer",
    "feedback_count",
    "date",
    "body_positionierung",
    "body_alleinstellung",
    "body_fuehrungsstil",
    "body_einsatzgebiete",
    "body_belastbarkeit",
    "body_zukunftskompetenz",
    "body_unternehmenskultur",
    "qr_url",     # URL die Canvas QR-Code-App in Bild umwandelt
]


def queue_entry_to_csv_row(entry: dict) -> dict:
    """Convert internal queue entry → flat CSV row matching CANVA_CSV_COLUMNS."""
    p = entry.get("payload", {})
    sections = p.get("sections", {})
    pruef = p.get("pruefnummer", "")
    pruef_full = pruef if pruef.startswith("#") else f"#{pruef}" if pruef else ""

    return {
        "person_name": p.get("person_name", ""),
        "header": p.get("header", ""),
        "pruefnummer": pruef_full,
        "feedback_count": str(p.get("feedback_count", "3")),
        "date": p.get("date") or datetime.now().strftime("%d.%m.%Y"),
        "body_positionierung":     sections.get("positionierung", ""),
        "body_alleinstellung":     sections.get("alleinstellung", ""),
        "body_fuehrungsstil":      sections.get("fuehrungsstil", ""),
        "body_einsatzgebiete":     sections.get("einsatzgebiete", ""),
        "body_belastbarkeit":      sections.get("belastbarkeit", ""),
        "body_zukunftskompetenz":  sections.get("zukunftskompetenz", ""),
        "body_unternehmenskultur": sections.get("unternehmenskultur", ""),
        "qr_url": p.get("verify_url",
            f"https://sx.staerkenkompass.de/verify.html?id={pruef.lstrip('#')}" if pruef else ""),
    }


def build_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CANVA_CSV_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for e in entries:
        writer.writerow(queue_entry_to_csv_row(e))
    return buf.getvalue()


# ─── HTTP HANDLER ─────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    def _send(self, status, ctype, body, headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=200, headers=None):
        self._send(status, "application/json; charset=utf-8",
                    json.dumps(data, ensure_ascii=False), headers)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n) if n else b""

    def _read_json(self):
        try:
            return json.loads(self._read_body() or "{}")
        except Exception:
            return {}

    def _session(self):
        return get_session(self.headers.get("Cookie"))

    def _require_auth(self):
        sess = self._session()
        if not sess:
            self._json({"error": "auth required"}, status=401)
            return None
        return sess

    # ─── ROUTING ───────────────────────────────────────────────────────────
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        # Pages
        if path in ("/", "/index.html"):
            sess = self._session()
            if sess:
                self._send(302, "text/plain", "", {"Location": "/editor"})
            else:
                self._serve_static(PUBLIC / "login.html")
            return
        if path == "/editor":
            if not self._session():
                self._send(302, "text/plain", "", {"Location": "/"}); return
            self._serve_static(PUBLIC / "editor.html"); return
        if path == "/bulk-queue":
            if not self._session():
                self._send(302, "text/plain", "", {"Location": "/"}); return
            self._serve_static(PUBLIC / "bulk-queue.html"); return
        if path == "/overview":
            if not self._session():
                self._send(302, "text/plain", "", {"Location": "/"}); return
            self._serve_static(PUBLIC / "overview.html"); return
        if path == "/verify.html":
            self._serve_static(PUBLIC / "verify.html"); return

        # Uploads (öffentlich erreichbar — Canva lädt von hier!)
        if path.startswith("/uploads/"):
            self._serve_static(UPLOADS / path[len("/uploads/"):]); return

        # API GETs
        if path == "/api/me":
            sess = self._session()
            self._json({"user": sess.get("user") if sess else None}); return

        if path == "/api/default-prompt":
            if not self._require_auth(): return
            try:
                from lib.claude_extractor import DEFAULT_SYSTEM_PROMPT
                self._json({"prompt": DEFAULT_SYSTEM_PROMPT})
            except Exception as e:
                self._json({"error": str(e)}, status=500)
            return

        if path == "/api/bulk-queue":
            if not self._require_auth(): return
            self._json(load_json(BULK_QUEUE_FILE, [])); return

        if path == "/api/export-csv":
            if not self._require_auth(): return
            queue = load_json(BULK_QUEUE_FILE, [])
            pending = [e for e in queue if e.get("status") != "exported"]
            if not pending:
                self._json({"error": "Keine SX in der Queue"}, status=404); return
            csv_data = build_csv(pending)
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            fname = f"sx-bulk-{ts}.csv"
            # Mark as exported
            for e in queue:
                if e in pending:
                    e["status"] = "exported"
                    e["exported_at"] = datetime.now().isoformat()
            save_json(BULK_QUEUE_FILE, queue)
            # Also append to long-term records
            recs = load_json(RECORDS_FILE, [])
            for e in pending:
                recs.append({**e, "csv_export": ts})
            save_json(RECORDS_FILE, recs)
            self._send(200, "text/csv; charset=utf-8", csv_data,
                       {"Content-Disposition": f'attachment; filename="{fname}"'})
            return

        if path == "/api/records":
            if not self._require_auth(): return
            self._json(load_json(RECORDS_FILE, [])); return

        if path == "/api/sponsors":
            if not self._require_auth(): return
            self._json(load_json(SPONSORS_FILE, [])); return

        if path == "/api/schirmherren":
            if not self._require_auth(): return
            data = load_json(DEFAULTS_FILE, None)
            if data is None:
                data = self._default_schirmherren()
            self._json(data); return

        # Static fallback
        target = PUBLIC / path.lstrip("/")
        if target.exists() and target.is_file():
            self._serve_static(target); return
        self._send(404, "text/plain", "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path

        if path == "/api/login":
            data = self._read_json()
            user = (data.get("username") or "").strip()
            pw = data.get("password") or ""
            if ACCOUNTS.get(user) and hmac.compare_digest(ACCOUNTS[user], pw):
                sid = make_session(user)
                self._json({"ok": True, "user": user},
                           headers={"Set-Cookie": f"sxid={sid}; HttpOnly; SameSite=Lax; Path=/"})
            else:
                self._json({"ok": False, "error": "Ungültiger Login"}, status=401)
            return

        if path == "/api/logout":
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            sid = cookie.get("sxid")
            # Signed cookies sind stateless — kein Server-State zum Löschen.
            # Cookie löschen reicht.
            self._json({"ok": True}, headers={"Set-Cookie": "sxid=; Max-Age=0; Path=/"})
            return

        # NEW: add SX to bulk queue
        if path == "/api/bulk-queue":
            if not self._require_auth(): return
            payload = self._read_json()
            entry = {
                "id": secrets.token_hex(8),
                "created_at": datetime.now().isoformat(),
                "created_by": self._session().get("user"),
                "status": "pending",
                "payload": payload,
            }
            queue = load_json(BULK_QUEUE_FILE, [])
            queue.append(entry)
            save_json(BULK_QUEUE_FILE, queue)
            self._json(entry); return

        if path == "/api/claim-prn":
            if not self._require_auth(): return
            pool = load_json(QR_POOL_FILE, None)
            if pool is None:
                pool = [{"prn": f"EU-DE-2026-{1000+i:04d}-{chr(65+i%26)}{chr(65+(i*3)%26)}",
                         "status": "Frei"} for i in range(50)]
                save_json(QR_POOL_FILE, pool)
            for entry in pool:
                if entry["status"] == "Frei":
                    entry["status"] = "Reserviert"
                    entry["reserved_at"] = datetime.now().isoformat()
                    entry["reserved_by"] = self._session().get("user")
                    save_json(QR_POOL_FILE, pool)
                    self._json({"prn": entry["prn"],
                                "verify_url": f"https://sx.staerkenkompass.de/verify.html?id={entry['prn']}"})
                    return
            self._json({"error": "QR-Pool erschöpft"}, status=503); return

        # ─── KI-Endpoints (Claude Vision + Text-Gen) ─────────────────────
        if path == "/api/import-from-screenshot":
            if not self._require_auth(): return
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("multipart/form-data"):
                self._json({"error": "multipart required"}, status=400); return
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                   environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype})
            file_field = fs["file"] if "file" in fs else None
            if file_field is None or not getattr(file_field, "filename", None):
                self._json({"error": "no file"}, status=400); return
            try:
                from lib.claude_extractor import (
                    extract_from_image, extract_from_pdf, smart_default_mapping
                )
                img_bytes = file_field.file.read()
                fname = file_field.filename.lower()
                if fname.endswith(".pdf"):
                    extracted = extract_from_pdf(img_bytes)
                else:
                    mime = "image/jpeg" if fname.endswith((".jpg", ".jpeg")) else "image/png"
                    extracted = extract_from_image(img_bytes, mime_type=mime)
                section_strengths = smart_default_mapping(extracted)
                self._json({
                    "vorname": extracted.get("vorname", ""),
                    "nachname": extracted.get("nachname", ""),
                    "dimensions": {k: extracted.get(k, []) for k in ["AE", "ED", "SH", "WK"]},
                    "section_strengths_default": section_strengths,
                })
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({"error": str(e)}, status=500)
            return

        if path == "/api/generate-texts":
            if not self._require_auth(): return
            try:
                from lib.claude_extractor import generate_section_texts
                body = self._read_json()
                section_strengths = body.get("section_strengths", {})
                vorname = body.get("vorname", "")
                nachname = body.get("nachname", "")
                # System-Prompt vom Editor (oben). Wenn leer/fehlt → Default.
                system_prompt = body.get("system_prompt") or None
                texts = generate_section_texts(section_strengths, vorname, nachname, system_prompt)
                self._json({"sections": texts})
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({"error": str(e)}, status=500)
            return

        if path == "/api/generate-headers":
            if not self._require_auth(): return
            try:
                from lib.claude_extractor import generate_header_alternatives
                body = self._read_json()
                section_strengths = body.get("section_strengths", {})
                vorname = body.get("vorname", "")
                alts = generate_header_alternatives(section_strengths, vorname)
                self._json({"alternatives": alts})
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({"error": str(e)}, status=500)
            return

        if path == "/api/upload":
            if not self._require_auth(): return
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("multipart/form-data"):
                self._json({"error": "multipart required"}, status=400); return
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                   environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype})
            file_field = fs["file"] if "file" in fs else None
            if file_field is None or not getattr(file_field, "filename", None):
                self._json({"error": "no file"}, status=400); return
            kind = fs.getvalue("kind", "misc")
            suffix = Path(file_field.filename).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}:
                self._json({"error": "Bildformat nicht unterstützt"}, status=400); return
            name = f"{kind}_{int(time.time()*1000)}_{secrets.token_hex(4)}{suffix}"
            target = UPLOADS / name
            target.write_bytes(file_field.file.read())
            self._json({"url": f"/uploads/{name}", "name": file_field.filename}); return

        if path == "/api/sponsors":
            if not self._require_auth(): return
            pool = load_json(SPONSORS_FILE, [])
            body = self._read_json()
            body["id"] = secrets.token_hex(6)
            body["created_at"] = datetime.now().isoformat()
            pool.append(body)
            save_json(SPONSORS_FILE, pool)
            self._json(body); return

        if path == "/api/schirmherren":
            if not self._require_auth(): return
            body = self._read_json()
            save_json(DEFAULTS_FILE, body)
            self._json({"ok": True}); return

        self._send(404, "text/plain", "Not Found")

    def do_DELETE(self):
        url = urlparse(self.path)
        path = url.path

        if path.startswith("/api/bulk-queue/"):
            if not self._require_auth(): return
            entry_id = path[len("/api/bulk-queue/"):]
            queue = load_json(BULK_QUEUE_FILE, [])
            queue = [e for e in queue if e.get("id") != entry_id]
            save_json(BULK_QUEUE_FILE, queue)
            self._json({"ok": True}); return

        if path == "/api/sponsors":
            if not self._require_auth(): return
            pool = load_json(SPONSORS_FILE, [])
            body = self._read_json()
            pool = [p for p in pool if p.get("id") != body.get("id")]
            save_json(SPONSORS_FILE, pool)
            self._json({"ok": True}); return

        self._send(404, "text/plain", "Not Found")

    def _get_user_prompt(self):
        """Hole den User-spezifischen Custom-Prompt. Fallback: Default."""
        sess = self._session()
        if not sess:
            return None
        prompts_file = DATA / "user_prompts.json"
        prompts = load_json(prompts_file, {})
        return prompts.get(sess.get("user")) or None

    def _serve_static(self, fpath: Path):
        if not fpath.exists() or not fpath.is_file():
            self._send(404, "text/plain", "Not Found"); return
        ctype, _ = mimetypes.guess_type(str(fpath))
        ctype = ctype or "application/octet-stream"
        self._send(200, ctype, fpath.read_bytes())

    def _default_schirmherren(self):
        return {
            "schirmherren": [
                {"name": "Prof. Dr. Claudia Gerhardt",
                 "title_lines": ["Leiterin Psychology School /",
                                 "Studiendekanin Wirtschaftspsychologie"],
                 "signature_url": "/assets/defaults/signature_CL_Gerhardt.png",
                 "logo_url": "/assets/defaults/logo_fresenius.png"},
                {"name": "Dr. Nicolas Bogs",
                 "title_lines": ["TANGRON Talent & Insight"],
                 "signature_url": "/assets/defaults/signature_NB_Bogs.png",
                 "logo_url": "/assets/defaults/logo_tangron.png"},
                {"name": "Torben Schacht",
                 "title_lines": ["Geschäftsführender Gesellschafter"],
                 "signature_url": "/assets/defaults/signature_TS_Schacht.png",
                 "logo_url": "/assets/defaults/staerkenkompass_logo.png"},
            ]
        }


def main():
    port = int(os.environ.get("PORT", 8000))
    addr = ("0.0.0.0", port)
    print(f"┌─────────────────────────────────────────────────────────")
    print(f"│ Stärkenkompass Content Server (Bulk-Queue Mode)")
    print(f"│ Port: {port}")
    print(f"│ Public Base URL: {PUBLIC_BASE_URL}")
    print(f"│ Login: Content1/ToHa01 … Content9/ToHa09")
    print(f"│ Routes: /editor /bulk-queue /overview")
    print(f"│ Export: /api/export-csv (CSV für Canva Bulk Create)")
    print(f"└─────────────────────────────────────────────────────────")
    ThreadingHTTPServer(addr, Handler).serve_forever()


if __name__ == "__main__":
    main()
