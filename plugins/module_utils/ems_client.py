# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""FortiClient EMS REST client. No Ansible imports so tools can reuse it."""
from __future__ import absolute_import, division, print_function
__metaclass__ = type

import time

try:
    import requests
    HAS_REQUESTS = True
    REQUESTS_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    requests = None
    HAS_REQUESTS = False
    REQUESTS_IMPORT_ERROR = str(exc)

try:
    from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_redact import redact
except ImportError:  # used by stand-alone tools
    from ems_redact import redact  # pragma: no cover

GLOBAL_SITE = "Global"
_RETRY_STATUS = (502, 503, 504)


class EMSError(Exception):
    def __init__(self, message, method=None, path=None, status=None, body=None):
        super(EMSError, self).__init__(message)
        self.message = message
        self.method = method
        self.path = path
        self.status = status
        self.body = redact(body) if body is not None else None

    def __str__(self):
        parts = [self.message]
        if self.method:
            parts.append("(%s %s, HTTP %s)" % (self.method, self.path, self.status))
        return " ".join(parts)


class EMSClient(object):
    def __init__(self, host, username, password, port=443, validate_certs=True,
                 timeout=30, site=None, session=None, sleep=time.sleep):
        self.host = host
        self.port = int(port)
        self._username = username
        self._password = password
        self.validate_certs = validate_certs
        self.timeout = timeout
        self.requested_site = site
        self.current_site = None
        self._sleep = sleep
        self._logged_in = False
        if session is None:
            if not HAS_REQUESTS:
                raise EMSError("The requests library is required: %s" % REQUESTS_IMPORT_ERROR)
            if not validate_certs:
                try:
                    requests.packages.urllib3.disable_warnings()
                except Exception:  # pragma: no cover
                    pass
            session = requests.Session()
        self.session = session
        # Referer must match the browser form: no explicit :443
        self.base = "https://%s" % host if self.port == 443 else "https://%s:%d" % (host, self.port)
        self.api = self.base + "/api/v1"

    # ---- transport -------------------------------------------------
    def _headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        token = None
        try:
            token = self.session.cookies.get("csrftoken")
        except Exception:
            token = None
        if token:
            h["X-CSRFToken"] = token
            h["Referer"] = self.base
        return h

    def send(self, method, path, json_body=None, params=None):
        """One raw call, no interpretation. Returns (status, parsed_json_or_None)."""
        kwargs = dict(headers=self._headers(), verify=self.validate_certs,
                      timeout=self.timeout, params=params)
        if json_body is not None:
            kwargs["json"] = json_body
        resp = self.session.request(method, self.api + path, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data

    def request(self, method, path, json_body=None, params=None):
        retries = 2 if method == "GET" else 0
        attempt = 0
        while True:
            try:
                status, data = self.send(method, path, json_body, params)
            except Exception as exc:  # transport error
                if attempt < retries:
                    attempt += 1
                    self._sleep(1)
                    continue
                raise EMSError("Connection error: %s" % type(exc).__name__, method, path, None)
            if status in _RETRY_STATUS and attempt < retries:
                attempt += 1
                self._sleep(1)
                continue
            break
        retval = None
        message = None
        if isinstance(data, dict):
            res = data.get("result") or {}
            retval = res.get("retval")
            message = res.get("message")
        if status >= 400 or retval != 1:
            raise EMSError("EMS request failed: %s" % (message or "no message"),
                           method, path, status, data)
        return data

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body=None):
        return self.request("POST", path, json_body=body if body is not None else {})

    def put(self, path, body=None):
        return self.request("PUT", path, json_body=body)

    def patch(self, path, body=None):
        return self.request("PATCH", path, json_body=body)

    def delete(self, path):
        return self.request("DELETE", path)

    # ---- session ---------------------------------------------------
    def login(self):
        # Credentials are never logged; no retry (lockout risk).
        try:
            status, data = self.send("POST", "/auth/signin",
                                     {"name": self._username, "password": self._password})
        except Exception as exc:
            raise EMSError("Connection error during login: %s" % type(exc).__name__)
        res = (data or {}).get("result") or {}
        if status >= 400 or res.get("retval") != 1:
            raise EMSError("Login failed: %s" % (res.get("message") or "HTTP %s" % status),
                           "POST", "/auth/signin", status)
        self._logged_in = True
        self.current_site = ((data or {}).get("data") or {}).get("site")
        if self.requested_site:
            self.switch_site(self.requested_site)
        return self

    def logout(self):
        if not self._logged_in:
            return
        self._logged_in = False
        try:
            self.send("POST", "/auth/signout", {})
        except Exception:
            pass

    def __enter__(self):
        return self.login()

    def __exit__(self, *exc):
        self.logout()
        return False

    def switch_site(self, display_name):
        if display_name == self.current_site:
            return
        self.post("/session/update", {"site": display_name})
        self.current_site = display_name

    # ---- sites -----------------------------------------------------
    def site_names(self):
        return self.get("/sites/names/index").get("data") or []

    def sites(self, include_global=False):
        data = self.get("/sites/index").get("data") or []
        return [s for s in data if include_global or not s.get("is_global")]

    def wait_operation(self, op_id, timeout=300, interval=1.0):
        deadline = time.time() + timeout
        while True:
            body = self.get("/sites/%s/poll" % op_id)
            d = body.get("data") or {}
            status = d.get("status")
            if status == 3:
                return d
            if status != 0:
                raise EMSError("Site operation failed (status %r)" % (status,),
                               "GET", "/sites/<op>/poll", 200, body)
            if time.time() >= deadline:
                raise EMSError("Timed out after %ss waiting for site operation" % timeout,
                               "GET", "/sites/<op>/poll", 200, body)
            self._sleep(interval)

    def wait_site_usable(self, display_name, timeout=300, interval=2.0):
        """A new site is listed and its create operation finished before the server accepts it
        as a session site ("invalid site name"). That error also poisons the session until a
        new login, so probe with throw-away sessions. Returns seconds waited."""
        start = time.time()
        while True:
            probe = EMSClient(self.host, self._username, self._password, port=self.port,
                              validate_certs=self.validate_certs, timeout=self.timeout)
            try:
                probe.login()
                probe.switch_site(display_name)
                probe.get("/workgroups/index")
                return time.time() - start
            except EMSError as exc:
                if exc.status != 400:
                    raise
            finally:
                probe.logout()
            if time.time() - start >= timeout:
                raise EMSError("Site '%s' did not become usable within %ss" % (display_name, timeout))
            self._sleep(interval)

    # ---- system ----------------------------------------------------
    def system_info(self):
        d = self.get("/system/info").get("data") or {}
        # the response also carries license identifiers: keep only what we need
        return {"name": d.get("name"), "system_time": d.get("system_time")}

    def system_version(self):
        """Spec route is /system/consts/get (data.System.VERSION*). On the tested EMS that call
        returns HTTP 500, so fall back to GET /system/version (data: "7.4.8.2245")."""
        try:
            d = (self.get("/system/consts/get").get("data") or {}).get("System") or {}
            if d.get("VERSION"):
                return {k: d.get(k) for k in ("VERSION", "VERSION_FULL", "VERSION_COMPARABLE")}
        except EMSError:
            pass
        full = self.get("/system/version").get("data")
        if not isinstance(full, str):
            raise EMSError("Could not determine the EMS version")
        nums = [int(x) for x in full.split(".")[:3]]
        nums += [0] * (3 - len(nums))
        return {"VERSION": ".".join(str(n) for n in nums[:3]), "VERSION_FULL": full,
                "VERSION_COMPARABLE": nums[0] * 1000000 + nums[1] * 1000 + nums[2]}
