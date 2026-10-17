"""End-to-end tests: the real modules and EMSClient against the simulated EMS server."""
import json

import pytest
from ansible.module_utils import basic

try:
    from ansible.module_utils.testing import patch_module_args
except ImportError:  # ansible-core < 2.19
    import contextlib
    from ansible.module_utils.common.text.converters import to_bytes

    @contextlib.contextmanager
    def patch_module_args(args):
        old = basic._ANSIBLE_ARGS
        basic._ANSIBLE_ARGS = to_bytes(json.dumps({"ANSIBLE_MODULE_ARGS": args}))
        try:
            yield
        finally:
            basic._ANSIBLE_ARGS = old

from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_client import EMSClient, EMSError
from ansible_collections.jurajama.forticlient_ems.plugins.modules import ems_info, ems_site, ems_workgroup
from conftest import USERNAME, PASSWORD


class Exit(Exception):
    def __init__(self, result, failed):
        self.result, self.failed = result, failed


@pytest.fixture
def run(mock_ems, monkeypatch):
    def _run(module, check_mode=False, **args):
        args.update(host="127.0.0.1", port=mock_ems.port, username=USERNAME, password=PASSWORD,
                    validate_certs=False, _ansible_check_mode=check_mode)

        def exit_json(self, **kw):
            raise Exit(kw, False)

        def fail_json(self, **kw):
            raise Exit(kw, True)
        monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
        monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)
        with patch_module_args(args), pytest.raises(Exit) as e:
            module.main()
        return e.value.result, e.value.failed
    return _run


def test_client_session_and_sites(live_client):
    assert live_client.current_site == "Global"
    assert live_client.system_version()["VERSION"] == "7.4.8"  # consts route 500s -> fallback
    assert [s["display_name"] for s in live_client.sites()] == ["Default"]
    assert live_client.sites(include_global=True)[0]["is_global"]
    live_client.switch_site("Default")
    names = [g["full_path"] for g in live_client.get("/workgroups/index")["data"]]
    assert names == ["All Groups", "All Groups/Other Endpoints"]


def test_bad_login_and_unknown_site(mock_ems):
    with pytest.raises(EMSError):
        EMSClient("127.0.0.1", "admin", "wrong", port=mock_ems.port, validate_certs=False).login()
    c = EMSClient("127.0.0.1", USERNAME, PASSWORD, port=mock_ems.port, validate_certs=False).login()
    with pytest.raises(EMSError) as e:
        c.switch_site("nope")
    assert e.value.status == 400


def test_polling_waits_for_pending_operation():
    from mock_ems.server import MockEMS
    with MockEMS(pending_polls=2) as srv:
        c = EMSClient("127.0.0.1", USERNAME, PASSWORD, port=srv.port, validate_certs=False,
                      sleep=lambda x: None).login()
        op = c.post("/sites/create", {"name": "slow"})["data"]["op_id"]
        assert c.wait_operation(op, interval=0)["status"] == 3
        assert sum(1 for m, p in srv.state.requests if p.endswith("/poll")) == 3


def test_info(run):
    res, failed = run(ems_info, gather_subset=["min", "sites"])
    assert not failed and res["version"] == "7.4.8" and res["hostname"] == "mock-ems"
    assert [s["display_name"] for s in res["sites"]] == ["Default"]
    assert "serial" not in json.dumps(res)


def test_site_lifecycle(run, mock_ems):
    res, _ = run(ems_site, check_mode=True, name="siteb")
    assert res["changed"] and "siteb" not in mock_ems.state.sites
    res, failed = run(ems_site, name="siteb")
    assert res["changed"] and not failed and res["site"]["display_name"] == "siteb"
    first_id = res["id"]
    res, _ = run(ems_site, name="siteb")
    assert not res["changed"] and res["id"] == first_id
    res, _ = run(ems_site, name="siteb", state="absent")
    assert res["changed"] and "siteb" not in mock_ems.state.sites
    res, _ = run(ems_site, name="siteb", state="absent")
    assert not res["changed"]
    res, failed = run(ems_site, name="Default", state="absent")
    assert failed and "built-in" in res["msg"]


def test_site_create_without_wait(run, mock_ems):
    res, failed = run(ems_site, name="async", wait=False)
    assert res["changed"] and res["op_id"] and not failed


def test_workgroup_lifecycle(run):
    run(ems_site, name="siteb")
    args = dict(site="siteb", name="VPN-group-1")
    res, _ = run(ems_workgroup, check_mode=True, **args)
    assert res["changed"]
    res, _ = run(ems_workgroup, **args)
    assert res["changed"] and res["workgroup"]["full_path"] == "All Groups/VPN-group-1"
    gid = res["workgroup"]["id"]
    res, _ = run(ems_workgroup, **args)
    assert not res["changed"] and res["workgroup"]["id"] == gid

    child = dict(site="siteb", name="child", parent="All Groups/VPN-group-1")
    res, _ = run(ems_workgroup, **child)
    assert res["changed"] and res["workgroup"]["full_path"] == "All Groups/VPN-group-1/child"
    res, _ = run(ems_workgroup, **child)
    assert not res["changed"]

    res, failed = run(ems_workgroup, site="siteb", name="x", parent="nope")
    assert failed
    res, failed = run(ems_workgroup, site="nosuchsite", name="x")
    assert failed and "Unknown site" in res["msg"]

    res, _ = run(ems_workgroup, state="absent", **child)
    assert res["changed"]
    res, _ = run(ems_workgroup, state="absent", **args)
    assert res["changed"]
    res, _ = run(ems_workgroup, state="absent", **args)
    assert not res["changed"]
    res, failed = run(ems_workgroup, site="siteb", name="Other Endpoints", state="absent")
    assert failed and "built-in" in res["msg"]
    res, _ = run(ems_workgroup, site="siteb", name="Other Endpoints")
    assert not res["changed"]


def test_workgroup_delete_refuses_group_with_devices(run, mock_ems):
    run(ems_workgroup, site="Default", name="busy")
    next(g for g in mock_ems.state.groups["Default"] if g["name"] == "busy")["total_devices"] = 3
    res, failed = run(ems_workgroup, site="Default", name="busy", state="absent")
    assert failed and "force" in res["msg"]
