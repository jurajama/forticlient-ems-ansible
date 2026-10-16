#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
module: ems_workgroup
short_description: Manage custom endpoint groups (workgroups) in a FortiClient EMS site
description:
  - Creates or deletes custom workgroups. A group is identified by its full path; renaming/moving is not supported.
extends_documentation_fragment:
  - jurajama.forticlient_ems.ems
options:
  site:
    description: Site display name to work in.
    type: str
    required: true
  name:
    description: Group name; must not contain C(/).
    type: str
    required: true
  parent:
    description: Full path of the parent group.
    type: str
    default: All Groups
  state:
    description: Desired state.
    type: str
    choices: [present, absent]
    default: present
  force:
    description:
      - With O(state=absent), attempt deletion even if the group has devices or an assigned policy.
    type: bool
    default: false
author:
  - jurajama (@jurajama)
'''

EXAMPLES = r'''
- jurajama.forticlient_ems.ems_workgroup:
    site: siteb
    name: VPN-group-1
'''

RETURN = r'''
workgroup:
  description: Group data (id, guid, name, full_path, parent_id, type, policy_id, policy_name, total_devices).
  returned: when the group exists or was created
  type: dict
'''

from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_common import (
    make_module, run, EMSError)

BUILTIN = 1
CUSTOM = 100


def summary(g, parent_id=None):
    pid = g.get("parent_id")
    if pid is None:
        ids = g.get("parent_ids") or []
        pid = ids[0] if ids else parent_id
    return dict(id=g.get("id"), guid=g.get("guid"), name=g.get("name"), full_path=g.get("full_path"),
                parent_id=pid, type=g.get("type"), policy_id=g.get("policy_id"),
                policy_name=g.get("policy_name"), total_devices=g.get("total_devices"))


def main():
    module = make_module(dict(
        site=dict(type="str", required=True),
        name=dict(type="str", required=True),
        parent=dict(type="str", default="All Groups"),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        force=dict(type="bool", default=False),
    ))
    p = module.params
    name = p["name"]
    if "/" in name:
        module.fail_json(msg="Group name must not contain '/'")
    path = p["parent"].rstrip("/") + "/" + name

    def work(client):
        groups = client.get("/workgroups/index").get("data") or []
        by_path = {g["full_path"]: g for g in groups}
        res = dict(changed=False)
        existing = by_path.get(path)

        if p["state"] == "present":
            if existing:
                res["workgroup"] = summary(existing)
                module.exit_json(**res)
            parent = by_path.get(p["parent"])
            if parent is None:
                raise EMSError("Parent group '%s' not found. Available: %s"
                               % (p["parent"], ", ".join(sorted(by_path))))
            res["changed"] = True
            diff = dict(before={}, after={"full_path": path})
            if module.check_mode:
                module.exit_json(diff=diff, **res)
            data = client.post("/workgroups/create", {"name": name, "parent_id": parent["id"]})["data"]
            if data.get("full_path") != path:
                raise EMSError("Created group has unexpected path '%s' (expected '%s')"
                               % (data.get("full_path"), path))
            res["workgroup"] = summary(data, parent["id"])
            module.exit_json(diff=diff, **res)

        if not existing:
            module.exit_json(**res)
        if existing.get("type") != CUSTOM:
            raise EMSError("'%s' is a built-in group and cannot be deleted" % path)
        if not p["force"] and ((existing.get("total_devices") or 0) > 0 or existing.get("policy_id") is not None):
            raise EMSError("Group '%s' has devices or an assigned policy; use force: true to attempt deletion" % path)
        res.update(changed=True, workgroup=summary(existing))
        diff = dict(before={"full_path": path}, after={})
        if module.check_mode:
            module.exit_json(diff=diff, **res)
        client.delete("/workgroups/%s/delete" % existing["id"])
        module.exit_json(diff=diff, **res)

    run(module, p["site"], work)


if __name__ == "__main__":
    main()
