#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, datetime, subprocess, re, zipfile, io, tempfile, json, uuid as _uuid
from werkzeug.utils import secure_filename
from flask import (
    Flask, request, jsonify, make_response, abort,
    render_template, render_template_string, send_from_directory,
    Response, send_file
)

APP = Flask(__name__, template_folder="templates", static_folder="www")

TOKEN       = os.environ.get("MS78_API_TOKEN", "muda_este_token")
READ_KEY    = os.environ.get("MS78_READ_KEY", "")
SYNC_TARGET = os.environ.get("SYNC_TARGET", "")

VAULT_PATH     = os.environ.get("VAULT_PATH", "/data/caderno")
DIARIOS_DIR    = os.path.join(VAULT_PATH, "diarios")
CHECKLIST_FILE = os.path.join(VAULT_PATH, "checklist.json")
WWW_DIR        = os.path.join(os.path.dirname(__file__), "www")

ALLOWED_EXT = {"png","jpg","jpeg","gif","webp","pdf","mp3","m4a","wav","ogg","flac"}

os.makedirs(DIARIOS_DIR, exist_ok=True)


# --- Utilitários ---
def _today_str():
    return datetime.date.today().isoformat()

def _today_dir():
    day = _today_str()
    folder = os.path.join(DIARIOS_DIR, day)
    os.makedirs(folder, exist_ok=True)
    return day, folder

def _append_diary_line(day, line):
    path = os.path.join(DIARIOS_DIR, f"{day}.md")
    new_file = not os.path.exists(path) or os.stat(path).st_size == 0
    with open(path, "a", encoding="utf-8") as f:
        if new_file:
            f.write(f"# Diário {day}\n\n⬛ CANAL\n\n✦ SATÉLITES\n\n⚡ RESUMO\n\n")
        f.write(line.rstrip() + "\n")

def safe_join(base, *paths):
    base_abs = os.path.realpath(base)
    final = os.path.realpath(os.path.join(base_abs, *paths))
    if final != base_abs and not final.startswith(base_abs + os.sep):
        raise ValueError("path traversal")
    return final

def check_auth(req):
    if TOKEN == "muda_este_token":
        return
    key = req.headers.get("X-MS78-Token") or req.args.get("token") or ""
    if key != TOKEN:
        abort(401)

def _hsize(n):
    for u in ["B","KB","MB","GB"]:
        if n < 1024: return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} TB"

@APP.after_request
def after_request(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-MS78-Token"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]  = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# --- Upload ---
@APP.route('/api/upload', methods=['POST','OPTIONS'])
@APP.route('/api/colagens/upload', methods=['POST','OPTIONS'])
def api_upload():
    if request.method == 'OPTIONS':
        return make_response("", 204)
    check_auth(request)
    if 'file' not in request.files:
        return jsonify(ok=False, error='No file'), 400
    file = request.files['file']
    if not file.filename:
        return jsonify(ok=False, error='Empty filename'), 400
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify(ok=False, error=f'extensão não permitida: .{ext}'), 400
    day, folder = _today_dir()
    ts = datetime.datetime.now().strftime('%H%M%S')
    save_name = f"{ts}_{filename}"
    file.save(os.path.join(folder, save_name))
    relpath = f"diarios/{day}/{save_name}"
    url = f"/arquivo/{relpath}"
    now = datetime.datetime.now().strftime('%H:%M')
    if ext in ("jpg","jpeg","png","webp"):
        _append_diary_line(day, f"- [{now}] 📎 {save_name}\n  ![[{relpath}]]")
    else:
        _append_diary_line(day, f"- [{now}] 📎 {save_name} — [[{relpath}]]")
    return jsonify(ok=True, filename=save_name, link=url, relpath=relpath)


# --- Ping ---
@APP.route("/api/ping")
def ping():
    return jsonify(ok=True, ts=datetime.datetime.now().isoformat())


# --- Chat / Escrita ---
@APP.route("/api/chat", methods=["POST","OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return make_response("", 204)
    check_auth(request)
    data = request.get_json(silent=True) or {}
    raw = (data.get("text") or "").strip()
    if not raw:
        return jsonify(ok=False, error="texto vazio"), 400

    now    = datetime.datetime.now()
    date_s = now.strftime("%Y-%m-%d")
    dayfile = os.path.join(DIARIOS_DIR, f"{date_s}.md")

    if not os.path.exists(dayfile):
        with open(dayfile, "w", encoding="utf-8") as f:
            f.write(f"# Diário {date_s}\n\n⬛ CANAL\n\n✦ SATÉLITES\n\n⚡ RESUMO\n")

    mode, body = "NOTA", raw
    patterns = {
        "SAT":        r"^\s*sat\s*:\s*(.*)$",
        "CANAL":      r"^\s*canal\s*:\s*(.*)$",
        "RESUMO":     r"^\s*resumo\s*:\s*(.*)$",
        "NOTA":       r"^\s*nota\s*:\s*(.*)$",
        "ALERTA":     r"^\s*alerta\s*:\s*(.*)$",
        "CONCLUIDO":  r"^\s*concluido\s*:\s*(.*)$",
        "IMPORTANTE": r"^\s*importante\s*:\s*(.*)$",
    }
    for m, pat in patterns.items():
        match = re.match(pat, raw, flags=re.IGNORECASE | re.DOTALL)
        if match:
            mode, body = m, match.group(1).strip()
            break

    replies = {
        "SAT":        "Registado como SATÉLITE. 🚀",
        "CANAL":      "Linha registada no CANAL. 📡",
        "RESUMO":     "Resumo anotado. ⚡",
        "NOTA":       "Nota registada. 📝",
        "ALERTA":     "Alerta registado. ⚠️",
        "CONCLUIDO":  "Tarefa concluída. ✅",
        "IMPORTANTE": "Marcado como Importante. 🔒",
    }
    reply = replies.get(mode, f"Recebi: {raw}")

    ts = now.strftime("## %H:%M:%S\n")
    with open(dayfile, "a", encoding="utf-8") as f:
        f.write(ts)
        icons = {"SAT":"✦ SATÉLITE","CANAL":"⬛ CANAL","RESUMO":"⚡ RESUMO",
                 "ALERTA":"⚠️ ALERTA","CONCLUIDO":"✅ CONCLUIDO","IMPORTANTE":"🔒 IMPORTANTE"}
        if mode in icons:
            first, *rest = body.splitlines()
            f.write(f"{icons[mode]} – {first.strip()}\n")
            for line in rest: f.write(line.rstrip() + "\n")
        else:
            f.write(f"📝 NOTA – {body}\n")
        f.write(f"{reply}\n\n")

    return jsonify(ok=True, reply=reply, saved=dayfile, mode=mode)


# --- Diários ---
@APP.route("/api/diarios/get")
def diarios_get():
    check_auth(request)
    date_s = (request.args.get("date") or datetime.datetime.now().strftime("%Y-%m-%d")).strip()
    try:
        datetime.datetime.strptime(date_s, "%Y-%m-%d")
    except ValueError:
        return jsonify(ok=False, error="date inválido"), 400
    path = os.path.join(DIARIOS_DIR, f"{date_s}.md")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Diário {date_s}\n\n")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify(ok=True, date=date_s, content=content)

@APP.route("/api/diarios/list")
def diarios_list():
    check_auth(request)
    try:
        n = int(request.args.get("n", 60))
    except ValueError:
        n = 60
    days = []
    try:
        for name in sorted(os.listdir(DIARIOS_DIR), reverse=True):
            if name.endswith(".md") and len(name) >= 13:
                days.append(name[:10])
    except FileNotFoundError:
        pass
    return jsonify(ok=True, days=days[:n])


# --- Exportar ---
@APP.route("/api/export/diarios")
def api_export_diarios():
    check_auth(request)
    if not os.path.isdir(DIARIOS_DIR):
        return jsonify(ok=False, error="pasta diarios não encontrada"), 404
    today = datetime.date.today().isoformat()
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False, dir="/tmp")
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
        for root, dirs, files in os.walk(DIARIOS_DIR):
            dirs.sort()
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, DIARIOS_DIR)
                zf.write(fpath, arcname)
    return send_file(tmp.name, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"diarios_{today}.zip")


# --- Sincronizar ---
@APP.route("/api/sync", methods=["POST"])
def api_sync():
    check_auth(request)
    if not SYNC_TARGET:
        return jsonify(ok=False, error="SYNC_TARGET não configurado no .env"), 400
    result = subprocess.run(
        ["rsync", "-az", "--delete", "--mkpath", VAULT_PATH + "/", SYNC_TARGET],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0:
        return jsonify(ok=True, reply="Sync concluído.")
    return jsonify(ok=False, error=result.stderr.strip() or "erro no sync"), 500


# --- Checklist ---
def _load_checklist():
    if not os.path.exists(CHECKLIST_FILE):
        return []
    try:
        with open(CHECKLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('items', [])
    except Exception:
        return []

def _save_checklist(items):
    with open(CHECKLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump({'items': items}, f, ensure_ascii=False, indent=2)

@APP.route('/checklist')
def checklist_page():
    return render_template('checklist.html')

@APP.route('/plano')
def plano_page():
    return render_template('plano.html')

@APP.route('/api/checklist', methods=['GET'])
def api_checklist_get():
    items = _load_checklist()
    today = datetime.date.today().isoformat()
    return jsonify(ok=True, items=items, today=today)

@APP.route('/api/checklist/add', methods=['POST', 'OPTIONS'])
def api_checklist_add():
    if request.method == 'OPTIONS':
        return make_response("", 204)
    check_auth(request)
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify(ok=False, error='texto vazio'), 400
    items = _load_checklist()
    date = (data.get('date') or datetime.date.today().isoformat()).strip()
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        date = datetime.date.today().isoformat()
    item = {
        'id': str(_uuid.uuid4())[:8],
        'text': text,
        'status': 'pending',
        'date': date
    }
    items.append(item)
    _save_checklist(items)
    return jsonify(ok=True, item=item)

@APP.route('/api/checklist/update', methods=['POST', 'OPTIONS'])
def api_checklist_update():
    if request.method == 'OPTIONS':
        return make_response("", 204)
    check_auth(request)
    data = request.get_json(silent=True) or {}
    item_id = data.get('id', '')
    status  = data.get('status', '')
    if status not in ('pending', 'done', 'abandoned', 'migrated'):
        return jsonify(ok=False, error='status inválido'), 400
    items = _load_checklist()
    today = datetime.date.today().isoformat()
    found = False
    removed = False
    for item in items:
        if item['id'] == item_id:
            if status == 'migrated' and item['date'] < today:
                # atrasado: migra imediatamente para hoje
                item['status'] = 'pending'
                item['date'] = today
            elif status == 'abandoned' and item['date'] < today:
                # atrasado abandonado: regista no diário original e remove
                _append_diary_line(item['date'], f"  ~ {item['text']}")
                items.remove(item)
                removed = True
            else:
                item['status'] = status
            found = True
            break
    if not found:
        return jsonify(ok=False, error='item não encontrado'), 404
    _save_checklist(items)
    return jsonify(ok=True, removed=removed)

@APP.route('/api/checklist/close', methods=['POST', 'OPTIONS'])
def api_checklist_close():
    if request.method == 'OPTIONS':
        return make_response("", 204)
    check_auth(request)
    data = request.get_json(silent=True) or {}
    date = data.get('date', datetime.date.today().isoformat())
    items = _load_checklist()
    pending = [i for i in items if i['date'] == date and i['status'] == 'pending']
    if pending:
        return jsonify(ok=False, error='ainda há items pendentes por resolver'), 400
    to_write = [i for i in items if i['date'] == date and i['status'] in ('done', 'abandoned')]
    if to_write:
        symbols = {'done': '×', 'abandoned': '~'}
        now = datetime.datetime.now().strftime('%H:%M')
        lines = '\n'.join(f"  {symbols[i['status']]} {i['text']}" for i in to_write)
        _append_diary_line(date, f"## {now}\n📋 Checklist\n{lines}")
    tomorrow = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
    new_items = []
    for i in items:
        if i['date'] == date:
            if i['status'] in ('done', 'abandoned'):
                continue  # remove — já no diário
            if i['status'] == 'migrated':
                i['status'] = 'pending'
                i['date'] = tomorrow
        new_items.append(i)
    _save_checklist(new_items)
    return jsonify(ok=True, closed=len(to_write))


# --- Pesquisa ---
@APP.route("/api/search")
def api_search():
    check_auth(request)
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify(ok=False, error="parâmetro q em falta"), 400
    try:
        n = min(int(request.args.get("n", 50)), 200)
    except ValueError:
        n = 50
    results = []
    try:
        files = sorted([f for f in os.listdir(DIARIOS_DIR) if f.endswith(".md")], reverse=True)
    except FileNotFoundError:
        files = []
    for fname in files:
        if len(results) >= n: break
        path = os.path.join(DIARIOS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        blocks = re.split(r"(?m)^##\s+(\d{2}:\d{2}:\d{2})\s*$", content)
        for i in range(1, len(blocks), 2):
            hhmmss, body = blocks[i], blocks[i+1]
            if q not in body.lower(): continue
            mode = "NOTA"
            for m_name, icon in [("SAT","✦"),("CANAL","⬛"),("RESUMO","⚡"),
                                  ("ALERTA","⚠️"),("CONCLUIDO","✅"),("IMPORTANTE","🔒")]:
                if icon in body:
                    mode = m_name; break
            results.append({"date": fname[:10], "time": hhmmss, "mode": mode,
                             "preview": "\n".join(body.strip().splitlines()[:5])})
            if len(results) >= n: break
    return jsonify(ok=True, q=q, total=len(results), results=results)


# --- Dashboard ---
@APP.route("/dashboard")
def dashboard():
    index = os.path.join(WWW_DIR, "index.html")
    if os.path.exists(index):
        return send_from_directory(WWW_DIR, "index.html")
    return "<h1>Ardósia MS78</h1><p><a href='/notas'>Notas</a></p>"

@APP.route("/notas")
def notas():
    return render_template("notas.html")

@APP.route("/")
def root():
    return dashboard()


# --- Arquivo ---
@APP.route("/arquivo/")
@APP.route("/arquivo/<path:subpath>")
@APP.route("/arquivo/<path:subpath>/")
def arquivo(subpath=""):
    rel = subpath.strip("/")
    try:
        abs_path = safe_join(VAULT_PATH, rel)
    except ValueError:
        abort(403)
    if not os.path.exists(abs_path):
        abort(404)
    if os.path.isfile(abs_path):
        if abs_path.lower().endswith('.md'):
            with open(abs_path, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype='text/plain; charset=utf-8')
        return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))
    items = []
    try:
        names = sorted(os.listdir(abs_path))
        dirs  = [n for n in names if os.path.isdir(os.path.join(abs_path, n))]
        files = [n for n in names if os.path.isfile(os.path.join(abs_path, n))]
        for name in dirs + files:
            full   = os.path.join(abs_path, name)
            is_dir = os.path.isdir(full)
            href   = "/arquivo/" + (rel + "/" if rel else "") + name + ("/" if is_dir else "")
            sufixo = "" if is_dir else f" — {_hsize(os.path.getsize(full))}"
            items.append({"name": name + ("/" if is_dir else ""), "href": href, "sufixo": sufixo})
    except PermissionError:
        abort(403)
    tpl = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arquivo — /{{ path or "" }}</title>
<style>
:root{--bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
      --accent:#00d4aa;--text:#e6edf3;--muted:#8b949e;--radius:10px;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;min-height:100vh;}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;height:52px;display:flex;align-items:center;justify-content:space-between;}
.logo{display:flex;align-items:center;gap:9px;}
.logo-icon{width:28px;height:28px;border-radius:7px;background:linear-gradient(135deg,#00d4aa,#0ea5e9);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;color:#000;}
.logo-text{font-weight:600;font-size:15px;}
a.back{color:var(--muted);font-size:13px;text-decoration:none;}
a.back:hover{color:var(--text);}
main{max-width:680px;margin:0 auto;padding:20px 16px;}
.breadcrumb{font-size:12px;color:var(--muted);margin-bottom:14px;}
.breadcrumb a{color:var(--muted);text-decoration:none;}
.breadcrumb a:hover{color:var(--text);}
.up-link{display:inline-block;margin-bottom:10px;color:var(--muted);text-decoration:none;font-size:13px;}
.up-link:hover{color:var(--text);}
.entry{display:flex;align-items:center;gap:10px;padding:9px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:6px;transition:border-color .15s;}
.entry:hover{border-color:var(--accent);}
.entry a{color:var(--text);text-decoration:none;flex:1;}
.entry a:hover{color:var(--accent);}
.size{font-size:11px;color:var(--muted);}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
</style></head>
<body>
<header>
  <div class="logo"><div class="logo-icon">MS</div><div class="logo-text">Ardósia</div></div>
  <a class="back" href="/dashboard">← dashboard</a>
</header>
<main>
  <div class="breadcrumb"><a href="/arquivo/">📂 arquivo</a>{% if path %} / {{ path }}{% endif %}</div>
  {% if path %}
    {% if '/' in path %}
      <a class="up-link" href="/arquivo/{{ path.rsplit('/',1)[0] }}/">⬆ pasta acima</a>
    {% else %}
      <a class="up-link" href="/arquivo/">⬆ arquivo</a>
    {% endif %}
  {% endif %}
  {% for e in entries %}
  <div class="entry">
    <a href="{{ e.href }}">{{ e.name }}</a>
    <span class="size">{{ e.sufixo }}</span>
  </div>
  {% endfor %}
  {% if not entries %}<p style="color:var(--muted);padding:20px 0">Pasta vazia.</p>{% endif %}
</main>
</body></html>"""
    return render_template_string(tpl, path=rel, entries=items)


# --- PWA ---
@APP.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Ardósia MS78",
        "short_name": "Ardósia",
        "description": "Caderno de campo MS78",
        "start_url": "/dashboard",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#000000",
        "theme_color": "#00ff00",
        "icons": [
            {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    })

@APP.route("/sw.js")
def service_worker():
    return Response("self.addEventListener('fetch', e => e.respondWith(fetch(e.request)));",
                    mimetype="application/javascript")

@APP.route("/icons/<path:filename>")
def icons(filename):
    return send_from_directory(os.path.join(WWW_DIR, "icons"), filename)


# --- Main ---
if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8787)
