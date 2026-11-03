#!/usr/bin/env python3
"""Local development server for the Counterparty site.

    bash tools/dev.sh                 first run creates .venv and installs the requirements, then this
    python3 tools/dev.py              build, serve on http://localhost:8000/bankCredit/, rebuild on every edit
    python3 tools/dev.py --open       the same, and open the browser
    python3 tools/dev.py --port 8080  another port (PORT in the environment works too)
    python3 tools/dev.py --public     the public view only, without the members file of agency ratings
    python3 tools/dev.py --once       build into site/, where the browser tests look, and exit

It never touches the committed data. A build rewrites data/json and appends to
data/history.parquet, both of which the pipeline owns, so this builds from its own copy of
data/ under .dev/ (ignored by git) and serves the site from .dev/site. A change under data/,
which is what a pull bringing the day's collection looks like, refreshes the copy.

What an edit costs:
  bankcredit/site/** (templates, CSS, JS)          the pages only, about five seconds
  any other bankcredit/*.py (export, score, ...)   the data export and the pages, about forty
  data/ (after a git pull)                         a fresh copy, the export and the pages

The browser reloads itself after each rebuild. A build that fails keeps the last good site and
shows the error in a bar at the foot of every page until the next good build.

The site is served under /bankCredit/, the address GitHub Pages publishes it at, so a link or a
fetch that escapes the site 404s here just as it would there.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEV = ROOT / ".dev"
SITE = DEV / "site"
BASE = "/bankCredit/"
POLL = 0.5                       # seconds between looks at the source tree
SETTLE = 0.4                     # an editor's save or a pull lands in several writes; wait them out

# Run in a fresh interpreter for every build, so an edited module is always the one that runs.
BUILD = r"""
import sys
from pathlib import Path
what, out = sys.argv[1], Path(sys.argv[2])
if what == "export":
    from bankcredit.export import export_json
    export_json()
import bankcredit.site.build as site
site.OUT = out
site.build()
"""

LEVELS = (None, "pages", "export", "data")


def level_of(paths) -> str | None:
    """How much a set of changed paths, relative to the repository root, makes us rebuild."""
    n = 0
    for p in paths:
        p = str(p).replace(os.sep, "/")
        if p.startswith("data/"):
            n = max(n, 3)
        elif p.startswith("bankcredit/site/"):
            n = max(n, 1)
        elif p.startswith("bankcredit/"):
            n = max(n, 2)
    return LEVELS[n]


def snapshot() -> dict[str, int]:
    """Modification times of everything a build reads: the code, and the committed data. The PDF
    cache is large and never read by a build; data/json is rebuilt from the tables, so a pull that
    changes it changes them too."""
    seen: dict[str, int] = {}
    for top in (ROOT / "bankcredit", DATA):
        for dirpath, dirnames, filenames in os.walk(top):
            here = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "cache") and not (here == DATA and d == "json")]
            for f in filenames:
                if f.startswith(".") or f.endswith((".pyc", ".log")):
                    continue
                p = here / f
                try:
                    seen[p.relative_to(ROOT).as_posix()] = p.stat().st_mtime_ns
                except FileNotFoundError:
                    pass                      # removed between the listing and the look
    return seen


def changed(before: dict[str, int], after: dict[str, int]) -> list[str]:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def _tail(text: str, n: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


def build(level: str, out: Path, swap: bool = True, attributed: bool = True) -> tuple[bool, str, float]:
    """Rebuild at `level` into `out`. With swap, the new site is built beside the old and moved into
    place only once it is complete, so the server never serves half a build and a failed build
    leaves the last good one standing. Returns (ok, error text, seconds)."""
    t = time.time()
    work = DEV / "data"
    try:
        if level == "data" or not work.exists():
            fresh = DEV / "data.next"
            shutil.rmtree(fresh, ignore_errors=True)
            shutil.copytree(DATA, fresh, ignore=shutil.ignore_patterns("cache"))
            shutil.rmtree(work, ignore_errors=True)
            fresh.rename(work)
    except OSError as exc:
        return False, f"could not copy data/ to {work}: {exc}", time.time() - t
    target = out.with_name(out.name + ".next") if swap else out
    env = dict(os.environ, BANKCREDIT_DATA=str(work), PYTHONPATH=str(ROOT))
    if attributed:
        env.setdefault("COUNTERPARTY_ATTRIBUTED", "1")      # the beta site carries the members file
    else:
        env.pop("COUNTERPARTY_ATTRIBUTED", None)
    what = "pages" if level == "pages" else "export"
    run = subprocess.run([sys.executable, "-c", BUILD, what, str(target)], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    if run.returncode != 0:
        if swap:
            shutil.rmtree(target, ignore_errors=True)
        return False, _tail(run.stderr or run.stdout), time.time() - t
    if swap:
        old = out.with_name(out.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        if out.exists():
            out.rename(old)
        target.rename(out)
        shutil.rmtree(old, ignore_errors=True)
    return True, "", time.time() - t


class State:
    """What the pages poll: a build number that moves only on a good build, and the last error."""

    def __init__(self):
        self.lock = threading.Lock()
        self.id = 0
        self.building = ""
        self.error = ""

    def start(self, level: str):
        with self.lock:
            self.building = level

    def finish(self, ok: bool, error: str):
        with self.lock:
            self.building = ""
            if ok:
                self.id += 1
                self.error = ""
            else:
                self.error = error

    def view(self) -> dict:
        with self.lock:
            return {"id": self.id, "building": self.building, "error": self.error}


STATE = State()

RELOAD = """<script>/* tools/dev.py: reload after a rebuild; show a failed one */(function(){
var id=null;
function show(kind,text){var b=document.getElementById("__dev");if(!text){if(b)b.remove();return}
if(!b){b=document.createElement("pre");b.id="__dev";document.body.appendChild(b)}
b.style.cssText=kind==="error"
?"position:fixed;left:0;right:0;bottom:0;max-height:45vh;overflow:auto;margin:0;padding:10px 16px;white-space:pre-wrap;font:12px/1.45 ui-monospace,Menlo,monospace;color:#fff;background:#7a1f1f;z-index:2147483647"
:"position:fixed;right:12px;bottom:12px;margin:0;padding:6px 10px;border-radius:6px;font:12px/1.2 ui-monospace,Menlo,monospace;color:#fff;background:#1e3a5f;z-index:2147483647";
b.textContent=text}
function poll(){fetch("/__dev__/build",{cache:"no-store"}).then(function(r){return r.json()}).then(function(s){
if(id===null)id=s.id;else if(s.id!==id){location.reload();return}
if(s.error)show("error","Build failed. This is the last good build.\\n\\n"+s.error);
else if(s.building)show("busy","rebuilding ("+s.building+")");else show("","")}).catch(function(){})
.then(function(){setTimeout(poll,1000)})}
poll()})();</script>"""

PLACEHOLDER = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Building</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font:16px/1.5 system-ui,sans-serif;margin:48px;color:#0c2340;background:#fff">
<h1 style="font-size:20px">Building the site</h1>
<p>The first build copies the data and exports it, about forty seconds. This page reloads when it is done.</p>
</body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the built site under /bankCredit/, with the reload script in every page."""

    def log_message(self, fmt, *args):
        pass                                  # the terminal is for builds, not for every request

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _redirect(self, where: str):
        self.send_response(302 if where == BASE else 301)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        return super().translate_path("/" + path[len(BASE):] if path.startswith(BASE) else path)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path == "/__dev__/build":
            return self._send(200, json.dumps(STATE.view()).encode(), "application/json")
        if path in ("/", BASE.rstrip("/")):
            return self._redirect(BASE)
        if not path.startswith(BASE):
            return self._send(404, b"Not under /bankCredit/, the address GitHub Pages serves the site at.\n",
                              "text/plain; charset=utf-8")
        site = Path(self.directory)
        if not (site / "index.html").exists():
            return self._send(200, (PLACEHOLDER.replace("</body>", RELOAD + "</body>")).encode(), "text/html; charset=utf-8")
        fs = Path(self.translate_path(self.path))
        if fs.is_dir():
            if not path.endswith("/"):
                return self._redirect(path + "/")
            fs = fs / "index.html"
        if fs.suffix == ".html" and fs.is_file():
            html = fs.read_text(encoding="utf-8")
            i = html.rfind("</body>")
            html = html[:i] + RELOAD + html[i:] if i >= 0 else html + RELOAD
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        return super().do_GET()


def _say(text: str):
    print(f"{time.strftime('%H:%M:%S')}  {text}", flush=True)


def watch(attributed: bool):
    """Build once from a fresh copy of the data, then rebuild whenever the source or the data moves.
    Edits made during a build are compared against the tree as it stood when the build began, so
    none is missed."""
    seen = snapshot()
    level = "data"
    while True:
        if level:
            STATE.start(level)
            _say(f"building ({level}) ...")
            ok, err, secs = build(level, SITE, attributed=attributed)
            STATE.finish(ok, err)
            if ok:
                _say(f"built ({level}) in {secs:.1f}s")
            else:
                _say(f"build failed ({level}) after {secs:.1f}s; still serving the last good build\n{err}\n")
        level = None
        time.sleep(POLL)
        now = snapshot()
        if changed(seen, now):
            time.sleep(SETTLE)
            now = snapshot()
            level = level_of(changed(seen, now))
            seen = now


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build, serve and rebuild the Counterparty site locally.")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--open", action="store_true", help="open the site in the browser once serving")
    ap.add_argument("--public", action="store_true", help="build without the members file of agency ratings")
    ap.add_argument("--once", action="store_true", help="build into site/ for the browser tests, then exit")
    a = ap.parse_args(argv)
    DEV.mkdir(exist_ok=True)

    if a.once:
        _say("building into site/ ...")
        ok, err, secs = build("data", ROOT / "site", swap=False, attributed=not a.public)
        _say(f"built in {secs:.1f}s" if ok else f"build failed after {secs:.1f}s\n{err}")
        return 0 if ok else 1

    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Handler, directory=str(SITE)))
    except OSError as exc:
        print(f"port {a.port} is not free ({exc}); try --port {a.port + 1}", file=sys.stderr)
        return 1
    httpd.daemon_threads = True
    url = f"http://localhost:{a.port}{BASE}"
    threading.Thread(target=watch, args=(not a.public,), daemon=True).start()
    _say(f"serving {url}  (Ctrl-C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        _say("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
