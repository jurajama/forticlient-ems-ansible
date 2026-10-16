# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Single redaction helper for EMS data (no Ansible imports)."""
from __future__ import absolute_import, division, print_function
__metaclass__ = type

import re

MASK = "<redacted>"

SECRET_KEYS = frozenset([
    "password", "passwd", "psk", "auth_data", "key", "secret", "token", "csrftoken",
    "cookie", "unreg_pwd", "lock", "temp_password", "disconnect_password",
    "sn", "hid",  # license identifiers
])

_ENC = re.compile(r"^Enc\s")
_BLOB = re.compile(r"^[A-Za-z0-9+/=]{80,}$")


def redact(obj):
    """Return a deep copy of a JSON-like structure with secrets masked."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SECRET_KEYS and v not in (None, "", False):
                out[k] = MASK
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and (_ENC.match(obj) or _BLOB.match(obj)):
        return MASK
    return obj
