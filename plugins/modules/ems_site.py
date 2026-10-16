#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
module: ems_site
short_description: Create or delete a FortiClient EMS site (tenant)
description:
  - Manages sites on a multi-site EMS. Runs in the Global context.
  - B(Deleting a site destroys all of its data.) The Default and Global sites can never be deleted.
  - Site updates (rename, licenses) are not supported by this module.
extends_documentation_fragment:
  - jurajama.forticlient_ems.ems
options:
  name:
    description: Site display name.
    type: str
    required: true
  state:
    description: Desired state.
    type: str
    choices: [present, absent]
    default: present
  licenses:
    description:
      - Seat counts used only when creating the site. Keys are fabric_agent, future_fabric_agent,
        sandbox_cloud, future_sandbox_cloud, sase, future_sase_user, edr, future_edr, forensics,
        future_forensics, chromebook, vpn_only. Each defaults to 0.
      - Ignored (with a warning) when the site already exists.
    type: dict
  wait:
    description: Wait for the asynchronous create/delete operation to finish.
    type: bool
    default: true
  wait_timeout:
    description: Seconds to wait for the operation.
    type: int
    default: 300
author:
  - jurajama (@jurajama)
'''

EXAMPLES = r'''
- jurajama.forticlient_ems.ems_site:
    name: siteb
    validate_certs: false

- jurajama.forticlient_ems.ems_site:
    name: siteb
    state: absent
'''

RETURN = r'''
id: {description: Numeric site id, returned: when the site exists or was created, type: int}
site: {description: Site summary, returned: when the site exists or was created, type: dict}
op_id: {description: Id of the asynchronous operation, returned: when an operation ran, type: str}
'''

from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_common import (
    make_module, run, GLOBAL_SITE, EMSError)

LICENSE_KEYS = ["fabric_agent", "future_fabric_agent", "sandbox_cloud", "future_sandbox_cloud",
                "sase", "future_sase_user", "edr", "future_edr", "forensics", "future_forensics",
                "chromebook", "vpn_only"]


def summary(s):
    return {k: s.get(k) for k in ("id", "name", "display_name", "is_default")}


def find_site(client, name):
    matches = [s for s in client.sites() if s.get("display_name") == name]
    if len(matches) > 1:
        raise EMSError("More than one site is named '%s'" % name)
    return matches[0] if matches else None


def create_body(name, licenses):
    unknown = sorted(set(licenses) - set(LICENSE_KEYS))
    if unknown:
        raise EMSError("Unknown license keys: %s" % ", ".join(unknown))
    body = {"license_ver": 1, "name": name}
    for k in LICENSE_KEYS:
        # EMS API names: <k>_licenses, except future_sase_user_licenses
        body["%s_licenses" % k] = int(licenses.get(k, 0))
    return body


def main():
    module = make_module(dict(
        name=dict(type="str", required=True),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        licenses=dict(type="dict"),
        wait=dict(type="bool", default=True),
        wait_timeout=dict(type="int", default=300),
    ))
    p = module.params
    name = p["name"]

    def work(client):
        check = module.check_mode
        site = find_site(client, name)
        res = dict(changed=False)
        if p["state"] == "present":
            if site:
                if p["licenses"]:
                    module.warn("License changes on an existing site are not supported; ignored.")
                res.update(id=site["id"], site=summary(site))
                module.exit_json(**res)
            res["changed"] = True
            if check:
                module.exit_json(diff=dict(before={}, after={"name": name}), **res)
            op = client.post("/sites/create", create_body(name, p["licenses"] or {}))["data"]["op_id"]
            res["op_id"] = op
            if p["wait"]:
                client.wait_operation(op, timeout=p["wait_timeout"])
                client.wait_site_usable(name, timeout=p["wait_timeout"])
                site = find_site(client, name)
                if not site:
                    raise EMSError("Site '%s' not found after the create operation finished" % name)
                res.update(id=site["id"], site=summary(site))
            module.exit_json(diff=dict(before={}, after={"name": name}), **res)

        # absent
        if not site:
            module.exit_json(**res)
        if site.get("is_default") or site.get("is_global"):
            raise EMSError("Refusing to delete the built-in site '%s'" % name)
        res.update(changed=True, id=site["id"], site=summary(site))
        if check:
            module.exit_json(diff=dict(before={"name": name}, after={}), **res)
        # module always runs in Global, so we are never inside the site being deleted
        op = client.delete("/sites/%s/delete" % site["id"])["data"]["op_id"]
        res["op_id"] = op
        if p["wait"]:
            client.wait_operation(op, timeout=p["wait_timeout"])
            if find_site(client, name):
                raise EMSError("Site '%s' still present after the delete operation finished" % name)
        module.exit_json(diff=dict(before={"name": name}, after={}), **res)

    run(module, GLOBAL_SITE, work)


if __name__ == "__main__":
    main()
