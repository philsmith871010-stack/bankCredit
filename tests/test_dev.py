"""The local development server (tools/dev.py): what an edit rebuilds, that a build is swapped in
whole or not at all, and what the server answers. The real build is exercised by running it; these
tests stand in a one-line build so they take a second rather than forty."""
from __future__ import annotations

import functools
import http.server
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("devserver", ROOT / "tools" / "dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


def test_an_edit_rebuilds_only_as_much_as_it_touches():
    assert dev.level_of(["bankcredit/site/assets/site.css"]) == "pages"
    assert dev.level_of(["bankcredit/site/components.py", "bankcredit/site/build.py"]) == "pages"
    assert dev.level_of(["bankcredit/export.py"]) == "export"
    assert dev.level_of(["bankcredit/site/build.py", "bankcredit/score.py"]) == "export"
    assert dev.level_of(["data/facts.parquet", "bankcredit/site/assets/app.js"]) == "data"
    assert dev.level_of(["docs/local-dev.md", "README.md"]) is None


def test_the_watch_ignores_what_a_build_never_reads(tmp_path, monkeypatch):
    for p in ("bankcredit/site/assets/site.css", "bankcredit/__pycache__/x.pyc", "data/facts.parquet",
              "data/cache/pdf/a.pdf", "data/json/board.json", "data/review/queue.json"):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("x")
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "DATA", tmp_path / "data")
    assert sorted(dev.snapshot()) == ["bankcredit/site/assets/site.css", "data/facts.parquet", "data/review/queue.json"]


def _sandbox(tmp_path, monkeypatch, code: str):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "facts.parquet").write_text("x")
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "DATA", tmp_path / "data")
    monkeypatch.setattr(dev, "DEV", tmp_path / ".dev")
    monkeypatch.setattr(dev, "BUILD", code)
    (tmp_path / ".dev").mkdir()
    return tmp_path / ".dev" / "site"


def test_a_good_build_replaces_the_site_and_builds_from_a_copy_of_the_data(tmp_path, monkeypatch):
    site = _sandbox(tmp_path, monkeypatch, "import os, sys, pathlib\n"
                    "out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True)\n"
                    "(out / 'index.html').write_text(os.environ['BANKCREDIT_DATA'])\n")
    site.mkdir(parents=True)
    (site / "index.html").write_text("old")
    ok, err, _ = dev.build("data", site)
    assert ok, err
    assert (site / "index.html").read_text() == str(tmp_path / ".dev" / "data")
    assert (tmp_path / ".dev" / "data" / "facts.parquet").exists()
    assert not site.with_name("site.next").exists() and not site.with_name("site.old").exists()


def test_a_failed_build_leaves_the_last_good_site_standing(tmp_path, monkeypatch):
    site = _sandbox(tmp_path, monkeypatch, "raise SystemExit('the template is broken')\n")
    site.mkdir(parents=True)
    (site / "index.html").write_text("last good")
    ok, err, _ = dev.build("pages", site)
    assert not ok and "the template is broken" in err
    assert (site / "index.html").read_text() == "last good"
    assert not site.with_name("site.next").exists()


@pytest.fixture()
def server(tmp_path):
    site = tmp_path / "site"
    (site / "tool").mkdir(parents=True)
    (site / "index.html").write_text("<html><body><p>landing</p></body></html>")
    (site / "tool" / "index.html").write_text("<html><body><p>tool</p></body></html>")
    (site / "data.json").write_text('{"a": 1}')
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(dev.Handler, directory=str(site)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        r = urllib.request.build_opener(NoRedirect).open(url)
        return r.status, r.headers, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()


def test_the_site_is_served_where_pages_serves_it_with_the_reload_script(server):
    code, headers, _ = _get(server + "/")
    assert code == 302 and headers["Location"] == "/bankCredit/"
    code, headers, body = _get(server + "/bankCredit/")
    assert code == 200 and "landing" in body and "/__dev__/build" in body
    assert body.index("/__dev__/build") < body.index("</body>"), "the script goes inside the body"
    assert headers["Cache-Control"] == "no-store"
    code, headers, _ = _get(server + "/bankCredit/tool")
    assert code == 301 and headers["Location"] == "/bankCredit/tool/", "relative links need the slash"
    code, _, body = _get(server + "/bankCredit/data.json")
    assert code == 200 and json.loads(body) == {"a": 1} and "__dev__" not in body
    code, _, _ = _get(server + "/data.json")
    assert code == 404, "a fetch that escapes the site fails here as it does on Pages"


def test_the_build_state_is_what_the_pages_poll(server):
    _, _, body = _get(server + "/__dev__/build")
    assert set(json.loads(body)) == {"id", "building", "error"}


def test_a_build_can_be_given_its_own_copy_of_the_data(tmp_path, monkeypatch):
    """The one-shot build for the tests and a running server each need their own copy: sharing one
    let the server rebuild its pages between the other build's copy and its export."""
    site = _sandbox(tmp_path, monkeypatch, "import os, sys, pathlib\n"
                    "out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True)\n"
                    "(out / 'index.html').write_text(os.environ['BANKCREDIT_DATA'])\n")
    own = tmp_path / ".dev" / "once-data"
    ok, err, _ = dev.build("data", site, swap=False, work=own)
    assert ok, err
    assert (site / "index.html").read_text() == str(own)
    assert (own / "facts.parquet").exists() and not (tmp_path / ".dev" / "data").exists()

