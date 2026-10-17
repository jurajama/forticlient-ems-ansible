"""Runs the maintainer integration playbook against the simulated EMS server."""
import os
import shutil
import subprocess

import pytest

from conftest import USERNAME, PASSWORD

PLAYBOOK = os.path.join(os.path.dirname(__file__), "..", "integration", "m1_site_workgroup.yml")


@pytest.mark.skipif(not shutil.which("ansible-playbook"), reason="ansible-playbook not installed")
def test_integration_playbook(mock_ems, tmp_path):
    env = dict(os.environ, EMS_SERVER="127.0.0.1", EMS_PORT=str(mock_ems.port),
               EMS_USERNAME=USERNAME, EMS_PASSWORD=PASSWORD, ANSIBLE_LOCALHOST_WARNING="false",
               ANSIBLE_HOME=str(tmp_path), ANSIBLE_NOCOLOR="1")
    r = subprocess.run(["ansible-playbook", PLAYBOOK], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True, timeout=300)
    assert r.returncode == 0, r.stdout
    assert "failed=0" in r.stdout and "siteb" not in mock_ems.state.sites
