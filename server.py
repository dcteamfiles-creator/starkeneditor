"""
SX Content Server — Flask app for Stärkenkompass content team.

Routes:
  /                     login form
  /editor               editor with live preview
  /overview             list of all generated SX
  /verify               public verification page
  /api/login            POST username+password
  /api/render           POST JSON → PDF bytes (used by editor + automation)
  /api/preview          POST JSON → PNG preview (lower-res, for live preview)
  /api/claim-prn        POST → next free Prüfnummer + verify_url
  /api/upload           POST file → returns blob URL (sponsor logos / signatures)
  /api/records          GET list of all SX, POST save new record
  /api/sponsors         GET pool of saved sponsor logos
  /api/schirmherren     GET defaults, POST save new

Auth: basic session cookie (HMAC-signed). 9 fixed accounts:
  Content1/ToHa01 ... Content9/ToHa09

Storage:
  - Google Sheets (QR pool + audit log) via service account
  - Local file storage for sponsor logos / signatures (./data/uploads/)
    [In production on Netlify, swap to @netlify/blobs]
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import time
from datetime import date, datetime
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pdf_renderer import render as render_pdf

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
RECORDS_FILE = DATA / "records.json"
DEFAULTS_FILE = DATA / "defaults.json"

UPLOADS.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(PUBLIC), static_url_path="")
app.secret_key = os.environ.get("SX_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

# ─── ACCOUNTS ──────────────────────────────────────────────────────────────
ACCOUNTS = {f"Content{i}": f"ToHa{i:02d}" for i in range(1, 10)}


# ─── AUTH ──────────────────────────────────────────────────────────────────
def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth required"}), 401
            return redirect("/")
        return view(*a, **kw)
    return wrapper


# ─── ROUTES: PAGES ─────────────────────────────────────────────────────────
@app.route("/")
def page_login():
    if session.get("user"):
        return redirect("/editor")
    return send_from_directory(PUBLIC, "login.html")


@app.route("/editor")
@login_required
def page_editor():
    return send_from_directory(PUBLIC, "editor.html")


@app.route("/overview")
@login_required
def page_overview():
    return send_from_directory(PUBLIC, "overview.html")


@app.route("/verify.html")
def page_verify():
    return send_from_directory(PUBLIC, "verify.html")


# ─── API: AUTH ─────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    user = data.get("username", "").strip()
    pw = data.get("password", "")
    if ACCOUNTS.get(user) and hmac.compare_digest(ACCOUNTS[user], pw):
        session["user"] = user
        return jsonify({"ok": True, "user": user})
    return jsonify({"ok": False, "error": "Ungültiger Login"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user", None)
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    return jsonify({"user": session.get("user")})


# ─── API: RENDER ───────────────────────────────────────────────────────────
def _normalize_payload(payload: dict) -> dict:
    """Resolve uploaded-file URLs to local paths for the renderer."""
    p = dict(payload)
    # Sponsor logo
    if p.get("sponsor_logo_url"):
        p["sponsor_logo_path"] = _url_to_path(p["sponsor_logo_url"])
    # Schirmherren
    sh = p.get("schirmherren") or []
    for s in sh:
        if isinstance(s, dict):
            if s.get("signature_url"):
                s["signature_path"] = _url_to_path(s["signature_url"])
            if s.get("logo_url"):
                s["logo_path"] = _url_to_path(s["logo_url"])
    return p


def _url_to_path(url: str) -> str:
    if url.startswith("/uploads/"):
        return str(UPLOADS / url[len("/uploads/"):])
    return url


@app.route("/api/render", methods=["POST"])
def api_render():
    """Public(ish) endpoint — used by editor AND future automation pipeline."""
    if not session.get("user") and request.headers.get("X-API-Key") != os.environ.get("SX_API_KEY"):
        return jsonify({"error": "auth required (session or X-API-Key)"}), 401
    payload = request.get_json(silent=True) or {}
    payload = _normalize_payload(payload)
    bleed = bool(payload.get("with_bleed", True))
    pdf_bytes = render_pdf(payload, with_bleed=bleed)
    fname = f"SX_{payload.get('person_name','SX').replace(' ', '-')}_{payload.get('pruefnummer','')}.pdf"
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


@app.route("/api/preview", methods=["POST"])
@login_required
def api_preview():
    """Lower-res PNG preview for editor."""
    import pypdfium2 as pdfium
    payload = _normalize_payload(request.get_json(silent=True) or {})
    pdf_bytes = render_pdf(payload, with_bleed=False)
    pdf = pdfium.PdfDocument(pdf_bytes)
    img = pdf[0].render(scale=1.4).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ─── API: QR POOL ──────────────────────────────────────────────────────────
@app.route("/api/claim-prn", methods=["POST"])
@login_required
def api_claim_prn():
    """Return next free Prüfnummer + verify URL.
    In production: read/write Google Sheet `SX-QR-Pool-Arbeitsdokument`.
    Local fallback: data/qr_pool.json
    """
    pool_file = DATA / "qr_pool.json"
    if not pool_file.exists():
        # Bootstrap a small pool for local testing
        pool = [{"prn": f"EU-DE-2026-{1000+i:04d}-{('XYAB'[i%4])}{('CDEF'[i%4])}",
                 "status": "Frei"} for i in range(50)]
        pool_file.write_text(json.dumps(pool, indent=2))
    pool = json.loads(pool_file.read_text())
    for entry in pool:
        if entry["status"] == "Frei":
            entry["status"] = "Reserviert"
            entry["reserved_at"] = datetime.now().isoformat()
            entry["reserved_by"] = session.get("user")
            pool_file.write_text(json.dumps(pool, indent=2))
            return jsonify({
                "prn": entry["prn"],
                "verify_url": f"https://sx.staerkenkompass.de/verify.html?id={entry['prn']}"
            })
    return jsonify({"error": "QR-Pool erschöpft. Neuen Pool erzeugen."}), 503


# ─── API: UPLOADS ──────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    f = request.files.get("file")
    kind = request.form.get("kind", "misc")  # sponsor / signature / logo
    if not f:
        return jsonify({"error": "no file"}), 400
    suffix = Path(f.filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        return jsonify({"error": "Nur PNG/JPG/WebP/SVG erlaubt"}), 400
    name = f"{kind}_{int(time.time()*1000)}_{secrets.token_hex(4)}{suffix}"
    target = UPLOADS / name
    f.save(target)
    return jsonify({"url": f"/uploads/{name}", "name": f.filename})


@app.route("/uploads/<path:name>")
def serve_upload(name):
    return send_from_directory(UPLOADS, name)


# ─── API: RECORDS (audit log) ──────────────────────────────────────────────
def _records():
    if RECORDS_FILE.exists():
        return json.loads(RECORDS_FILE.read_text())
    return []


def _save_record(rec):
    recs = _records()
    recs.append(rec)
    RECORDS_FILE.write_text(json.dumps(recs, indent=2))


@app.route("/api/records", methods=["GET", "POST"])
@login_required
def api_records():
    if request.method == "GET":
        return jsonify(_records())
    rec = request.get_json(silent=True) or {}
    rec["id"] = secrets.token_hex(8)
    rec["created_at"] = datetime.now().isoformat()
    rec["created_by"] = session.get("user")
    _save_record(rec)
    return jsonify(rec)


# ─── API: SPONSORS POOL ────────────────────────────────────────────────────
SPONSORS_FILE = DATA / "sponsors.json"


@app.route("/api/sponsors", methods=["GET", "POST", "DELETE"])
@login_required
def api_sponsors():
    pool = json.loads(SPONSORS_FILE.read_text()) if SPONSORS_FILE.exists() else []
    if request.method == "GET":
        return jsonify(pool)
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        body["id"] = secrets.token_hex(6)
        body["created_at"] = datetime.now().isoformat()
        pool.append(body)
        SPONSORS_FILE.write_text(json.dumps(pool, indent=2))
        return jsonify(body)
    if request.method == "DELETE":
        body = request.get_json(silent=True) or {}
        pool = [p for p in pool if p.get("id") != body.get("id")]
        SPONSORS_FILE.write_text(json.dumps(pool, indent=2))
        return jsonify({"ok": True})


# ─── API: SCHIRMHERREN DEFAULTS ────────────────────────────────────────────
@app.route("/api/schirmherren", methods=["GET", "PUT"])
@login_required
def api_schirmherren():
    if request.method == "GET":
        if DEFAULTS_FILE.exists():
            return jsonify(json.loads(DEFAULTS_FILE.read_text()))
        # Return baked-in defaults
        return jsonify({
            "schirmherren": [
                {"name": "Prof. Dr. Claudia Gerhardt",
                 "title_lines": ["Leiterin Psychology School /",
                                 "Studiendekanin Wirtschaftspsychologie"],
                 "signature_url": None, "logo_url": None},
                {"name": "Dr. Nicolas Bogs",
                 "title_lines": ["TANGRON Talent & Insight"],
                 "signature_url": None, "logo_url": None},
                {"name": "Torben Schacht",
                 "title_lines": ["Geschäftsführender Gesellschafter"],
                 "signature_url": None, "logo_url": None},
            ]
        })
    body = request.get_json(silent=True) or {}
    DEFAULTS_FILE.write_text(json.dumps(body, indent=2))
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
