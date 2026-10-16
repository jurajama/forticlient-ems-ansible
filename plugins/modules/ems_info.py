#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
module: ems_info
short_description: Gather facts about a FortiClient EMS server
description:
  - Returns version, host name, time and optionally the list of sites. Read-only, also usable as connectivity test.
extends_documentation_fragment:
  - jurajama.forticlient_ems.ems
options:
  gather_subset:
    description: V(min) is always gathered; V(sites) adds the site list.
    type: list
    elements: str
    choices: [min, sites]
    default: [min]
author:
  - jurajama (@jurajama)
'''

EXAMPLES = r'''
- jurajama.forticlient_ems.ems_info:
    gather_subset: [sites]
    validate_certs: false
  register: ems
'''

RETURN = r'''
hostname: {description: EMS host name, returned: always, type: str}
system_time: {description: EMS system time, returned: always, type: str}
version: {description: Short version, returned: always, type: str, sample: "7.4.8"}
version_full: {description: Full version, returned: always, type: str}
version_comparable: {description: Numeric version, returned: always, type: int}
current_site: {description: Site context used (always Global), returned: always, type: str}
sites:
  description: Sites, global pseudo-site excluded.
  returned: when gather_subset includes sites
  type: list
  elements: dict
'''

from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_common import (
    make_module, run, GLOBAL_SITE)


def site_summary(s):
    return {k: s.get(k) for k in ("id", "name", "display_name", "is_default")}


def main():
    module = make_module(dict(
        gather_subset=dict(type="list", elements="str", choices=["min", "sites"], default=["min"]),
    ))

    def work(client):
        info = client.system_info()
        ver = client.system_version()
        res = dict(changed=False, hostname=info["name"], system_time=info["system_time"],
                   version=ver["VERSION"], version_full=ver["VERSION_FULL"],
                   version_comparable=ver["VERSION_COMPARABLE"], current_site=GLOBAL_SITE)
        if "sites" in module.params["gather_subset"]:
            res["sites"] = [site_summary(s) for s in client.sites()]
        module.exit_json(**res)

    run(module, GLOBAL_SITE, work)


if __name__ == "__main__":
    main()
