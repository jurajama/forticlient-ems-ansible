import json
import pytest
from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_client import EMSClient, EMSError
from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_redact import redact


class Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        if self._b is None:
            raise ValueError
        return self._b


class Sess:
    def __init__(self, handler):
        self.h, self.calls, self.cookies = handler, [], {"csrftoken": "tok"}

    def request(self, method, url, **kw):
        self.calls.append((method, url.split("/api/v1")[1], kw))
        return self.h(method, url.split("/api/v1")[1], kw)


def ok(data=None):
    return Resp(200, {"result": {"retval": 1, "message": None}, "data": data})


def client(handler):
    s = Sess(handler)
    return EMSClient("h", "u", "secretpw", session=s, sleep=lambda x: None), s


def test_login_switch_and_headers():
    c, s = client(lambda m, p, kw: ok({"site": "Default"}) if p == "/auth/signin" else ok({"changed": True}))
    c.login()
    c.switch_site("Default")  # no-op
    c.switch_site("sitea")
    assert [x[1] for x in s.calls] == ["/auth/signin", "/session/update"]
    h = s.calls[-1][2]["headers"]
    assert h["X-CSRFToken"] == "tok" and h["Referer"] == "https://h"


def test_no_write_retry_and_secret_free_error():
    n = []

    def h(m, p, kw):
        n.append(p)
        return Resp(500, {"result": {"retval": -2, "message": "boom"}, "data": {"password": "secretpw"}})
    c, _s = client(h)
    with pytest.raises(EMSError) as e:
        c.post("/x", {})
    assert len(n) == 1 and "secretpw" not in str(e.value) and "secretpw" not in json.dumps(e.value.body)


def test_get_retries_on_503():
    seq = iter([Resp(503, None), Resp(503, None), ok([])])
    c, _s = client(lambda m, p, kw: next(seq))
    assert c.get("/x")["data"] == []


def test_wait_operation_states():
    seq = iter([ok({"status": 0}), ok({"status": 3, "progress": 100})])
    c, _s = client(lambda m, p, kw: next(seq))
    assert c.wait_operation("op")["status"] == 3
    c, _s = client(lambda m, p, kw: ok({"status": 99}))
    with pytest.raises(EMSError):
        c.wait_operation("op")


def test_redact():
    assert redact({"a": {"psk": "x", "name": "n"}, "e": "Enc abc"}) == {"a": {"psk": "<redacted>", "name": "n"}, "e": "<redacted>"}
