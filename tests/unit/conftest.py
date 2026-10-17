import os
import sys

import pytest

from ansible_collections.jurajama.forticlient_ems.plugins.module_utils.ems_client import EMSClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mock_ems.server import MockEMS, USERNAME, PASSWORD  # noqa: E402


@pytest.fixture
def mock_ems():
    with MockEMS() as server:
        yield server


@pytest.fixture
def live_client(mock_ems):
    c = EMSClient("127.0.0.1", USERNAME, PASSWORD, port=mock_ems.port, validate_certs=False,
                  timeout=10, sleep=lambda x: None)
    with c:
        yield c
