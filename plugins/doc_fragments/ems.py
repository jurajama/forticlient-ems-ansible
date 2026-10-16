# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type


class ModuleDocFragment(object):
    DOCUMENTATION = r'''
options:
  host:
    description: EMS host name or IP. Falls back to the E(EMS_SERVER) environment variable.
    type: str
  port:
    description: HTTPS port of the EMS API.
    type: int
    default: 443
  username:
    description: Global administrator name. Falls back to E(EMS_USERNAME).
    type: str
  password:
    description: Administrator password. Falls back to E(EMS_PASSWORD).
    type: str
  validate_certs:
    description: Validate the EMS TLS certificate. Falls back to E(EMS_VALIDATE_CERTS).
    type: bool
    default: true
  timeout:
    description: HTTP timeout in seconds.
    type: int
    default: 30
requirements:
  - requests
'''
