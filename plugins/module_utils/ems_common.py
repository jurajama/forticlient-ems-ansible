# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule, env_fallback, missing_required_lib
from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_client import (
    EMSClient, EMSError, HAS_REQUESTS, REQUESTS_IMPORT_ERROR, GLOBAL_SITE)


def ems_argument_spec():
    return dict(
        host=dict(type="str", fallback=(env_fallback, ["EMS_SERVER"])),
        port=dict(type="int", default=443),
        username=dict(type="str", fallback=(env_fallback, ["EMS_USERNAME"])),
        password=dict(type="str", no_log=True, fallback=(env_fallback, ["EMS_PASSWORD"])),
        validate_certs=dict(type="bool", default=True, fallback=(env_fallback, ["EMS_VALIDATE_CERTS"])),
        timeout=dict(type="int", default=30),
    )


def make_module(argument_spec, **kwargs):
    spec = ems_argument_spec()
    spec.update(argument_spec)
    kwargs.setdefault("supports_check_mode", True)
    module = AnsibleModule(argument_spec=spec, **kwargs)
    for k in ("host", "username", "password"):
        if not module.params.get(k):
            module.fail_json(msg="Parameter '%s' (or its EMS_* environment variable) is required" % k)
    if not HAS_REQUESTS:
        module.fail_json(msg=missing_required_lib("requests"), exception=REQUESTS_IMPORT_ERROR)
    return module


def build_client(module, site=None):
    """Login; if `site` is given switch into it (display name), after validating it exists."""
    p = module.params
    client = EMSClient(p["host"], p["username"], p["password"], port=p["port"],
                       validate_certs=p["validate_certs"], timeout=p["timeout"])
    client.login()
    if site is not None:
        if site not in (GLOBAL_SITE, "Default") and site not in client.site_names():
            names = client.site_names()
            raise EMSError("Unknown site '%s'. Available sites: %s" % (site, ", ".join(names)))
        client.switch_site(site)
    return client


def fail_from(module, exc, **extra):
    out = dict(msg=str(exc))
    if isinstance(exc, EMSError):
        out["ems_message"] = exc.message
        out["http_status"] = exc.status
    out.update(extra)
    module.fail_json(**out)


def run(module, site, func):
    """Run func(client) with guaranteed logout and uniform error handling."""
    client = None
    try:
        client = build_client(module, site)
        return func(client)
    except EMSError as exc:
        fail_from(module, exc)
    finally:
        if client is not None:
            client.logout()
