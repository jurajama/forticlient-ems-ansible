"""Minimal simulated FortiClient EMS 7.4 REST server for tests (stdlib only, HTTPS, self-signed).

Implements just the routes the collection uses: auth, session/update, system info/version,
sites (create/delete as asynchronous operations) and workgroups. Not a faithful EMS clone.

Stand-alone:  python3 tests/mock_ems/server.py [port]    (login admin / admin)
"""
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

USERNAME, PASSWORD = "admin", "admin"
VERSION_FULL = "7.4.8.2245"


def _ok(data=None):
    return 200, {"result": {"retval": 1, "message": None}, "data": data}


def _err(status, message):
    return status, {"result": {"retval": -1, "message": message}, "data": None}


class State(object):
    """All server state; one lock serialises requests."""

    def __init__(self, pending_polls=0):
        self.lock = threading.RLock()
        self.pending_polls = pending_polls  # polls answered "running" before an operation finishes
        self.next_id = 100
        self.sessions = {}  # session id -> {"site": str, "token": str}
        self.sites = {}     # display_name -> site dict
        self.ops = {}       # op id -> {"polls": int, "done": callable}
        self.groups = {}    # display_name -> list of group dicts
        self.requests = []  # (method, path) log for assertions
        self._add_site("Global", is_global=True)
        self._add_site("Default", is_default=True)

    def _new_id(self):
        self.next_id += 1
        return self.next_id

    def _add_site(self, name, is_default=False, is_global=False):
        sid = self._new_id()
        self.sites[name] = dict(id=sid, name="site%d" % sid, display_name=name,
                                is_default=is_default, is_global=is_global, usable=True)
        if not is_global:
            root = self._group("All Groups", None, 1)
            other = self._group("Other Endpoints", "All Groups", 1)
            other["parent_id"] = root["id"]
            self.groups[name] = [root, other]
        return self.sites[name]

    def _group(self, name, parent, gtype):
        path = name if parent is None else "%s/%s" % (parent, name)
        return dict(id=self._new_id(), guid=str(uuid.uuid4()), name=name, full_path=path,
                    parent_id=None, type=gtype, policy_id=None, policy_name=None, total_devices=0)

    def _op(self, done):
        op = "op-%d" % self._new_id()
        self.ops[op] = dict(polls=0, done=done)
        return op

    # ---- route handlers: return (status, body) ----------------------
    def handle(self, method, path, body, session):
        with self.lock:
            self.requests.append((method, path))
            for (m, pattern), fn in ROUTES:
                match = m == method and re.fullmatch(pattern, path)
                if match:
                    return fn(self, session, body, *match.groups())
            return _err(404, "no such route")

    def signin(self, session, body):
        if body.get("name") != USERNAME or body.get("password") != PASSWORD:
            return _err(401, "Invalid username or password")
        session["site"] = "Global"
        session["auth"] = True
        return _ok({"site": "Global"})

    def signout(self, session, body):
        session["auth"] = False
        return _ok()

    def session_update(self, session, body):
        site = self.sites.get(body.get("site"))
        if site is None or not site["usable"]:
            session["poisoned"] = True  # like the real server: needs a new login
            return _err(400, "invalid site name")
        if session.get("poisoned"):
            return _err(400, "invalid site name")
        session["site"] = site["display_name"]
        return _ok({"changed": True})

    def system_info(self, session, body):
        return _ok({"name": "mock-ems", "system_time": "2026-01-01 00:00:00", "serial": "FCTEMS000"})

    def system_consts(self, session, body):
        return _err(500, "internal error")  # mirrors the tested real EMS

    def system_version(self, session, body):
        return _ok(VERSION_FULL)

    def site_names(self, session, body):
        return _ok([n for n, s in self.sites.items() if not s["is_global"]])

    def site_index(self, session, body):
        return _ok([{k: v for k, v in s.items() if k != "usable"} for s in self.sites.values()])

    def site_create(self, session, body):
        name = body.get("name")
        if not name or name in self.sites:
            return _err(400, "site name invalid or already exists")
        site = self._add_site(name)
        site["usable"] = False
        return _ok({"op_id": self._op(lambda: site.update(usable=True))})

    def site_delete(self, session, body, sid):
        for name, s in list(self.sites.items()):
            if str(s["id"]) == sid:
                if s["is_default"] or s["is_global"]:
                    return _err(400, "cannot delete built-in site")
                return _ok({"op_id": self._op(lambda: (self.sites.pop(name), self.groups.pop(name)))})
        return _err(404, "site not found")

    def poll(self, session, body, op_id):
        op = self.ops.get(op_id)
        if op is None:
            return _err(404, "unknown operation")
        if op["polls"] < self.pending_polls:
            op["polls"] += 1
            return _ok({"status": 0})
        if op["done"]:
            op["done"]()
            op["done"] = None
        return _ok({"status": 3, "progress": 100})

    def _groups(self, session):
        return self.groups[session["site"]] if session["site"] in self.groups else None

    def wg_index(self, session, body):
        groups = self._groups(session)
        if groups is None:
            return _err(400, "workgroups are not available in the Global site")
        return _ok([dict(g) for g in groups])

    def wg_create(self, session, body):
        groups = self._groups(session)
        if groups is None:
            return _err(400, "workgroups are not available in the Global site")
        parent = next((g for g in groups if g["id"] == body.get("parent_id")), None)
        name = body.get("name")
        if parent is None or not name or "/" in name:
            return _err(400, "invalid parent or name")
        if any(g["full_path"] == "%s/%s" % (parent["full_path"], name) for g in groups):
            return _err(400, "group already exists")
        g = self._group(name, parent["full_path"], 100)
        g["parent_id"] = parent["id"]
        groups.append(g)
        return _ok(dict(g))

    def wg_delete(self, session, body, gid):
        groups = self._groups(session) or []
        g = next((g for g in groups if str(g["id"]) == gid), None)
        if g is None:
            return _err(404, "group not found")
        if g["type"] != 100:
            return _err(400, "built-in group")
        if any(x["full_path"].startswith(g["full_path"] + "/") for x in groups):
            return _err(400, "group has children")
        groups.remove(g)
        return _ok()


ROUTES = [
    (("POST", "/auth/signin"), State.signin),
    (("POST", "/auth/signout"), State.signout),
    (("POST", "/session/update"), State.session_update),
    (("GET", "/system/info"), State.system_info),
    (("GET", "/system/consts/get"), State.system_consts),
    (("GET", "/system/version"), State.system_version),
    (("GET", "/sites/names/index"), State.site_names),
    (("GET", "/sites/index"), State.site_index),
    (("POST", "/sites/create"), State.site_create),
    (("DELETE", r"/sites/(\w+)/delete"), State.site_delete),
    (("GET", r"/sites/(op-\d+)/poll"), State.poll),
    (("GET", "/workgroups/index"), State.wg_index),
    (("POST", "/workgroups/create"), State.wg_create),
    (("DELETE", r"/workgroups/(\d+)/delete"), State.wg_delete),
]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _serve(self):
        srv = self.server
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        path = self.path.split("?")[0]
        if not path.startswith("/api/v1"):
            return self._send(404, {"result": {"retval": -1, "message": "not found"}}, {})
        path = path[len("/api/v1"):]
        cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
        headers = {}
        sid = cookies.get("sessionid")
        with srv.state.lock:
            session = srv.state.sessions.get(sid)
            if path == "/auth/signin" or session is None:
                if path != "/auth/signin":
                    return self._send(401, {"result": {"retval": -1, "message": "not logged in"}}, {})
                sid, token = uuid.uuid4().hex, uuid.uuid4().hex
                session = srv.state.sessions[sid] = dict(site="Global", token=token)
                headers["Set-Cookie"] = ["sessionid=%s; Path=/" % sid, "csrftoken=%s; Path=/" % token]
            elif self.headers.get("X-CSRFToken") != session["token"] or not self.headers.get("Referer"):
                return self._send(403, {"result": {"retval": -1, "message": "CSRF check failed"}}, {})
            elif not session.get("auth") and path != "/auth/signout":
                return self._send(401, {"result": {"retval": -1, "message": "not logged in"}}, {})
        status, out = srv.state.handle(self.command, path, body, session)
        if path == "/auth/signin" and status != 200:
            srv.state.sessions.pop(sid, None)
        self._send(status, out, headers)

    def _send(self, status, body, headers):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for k, v in headers.items():
            for item in (v if isinstance(v, list) else [v]):
                self.send_header(k, item)
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _serve


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MockEMS(object):
    """Context manager: starts the server on a free (or given) port. `.port`, `.state`."""

    def __init__(self, port=0, pending_polls=0):
        self.state = State(pending_polls)
        self._tmp = tempfile.mkdtemp(prefix="mock-ems-")
        cert, key = os.path.join(self._tmp, "c.pem"), os.path.join(self._tmp, "k.pem")
        subprocess.check_call(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=localhost",
             "-keyout", key, "-out", cert], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._httpd = _Server(("127.0.0.1", port), _Handler)
        self._httpd.state = self.state
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        self._httpd.socket = ctx.wrap_socket(self._httpd.socket, server_side=True)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


if __name__ == "__main__":
    import sys
    with MockEMS(int(sys.argv[1]) if len(sys.argv) > 1 else 8443) as m:
        print("Mock EMS on https://127.0.0.1:%d (admin/admin)" % m.port)
        threading.Event().wait()
