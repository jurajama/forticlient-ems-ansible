# jurajama.forticlient_ems

Ansible modules for FortiClient EMS 7.4.x (multi-site). M1: `ems_info`, `ems_site`, `ems_workgroup`.
Credentials: `EMS_SERVER`, `EMS_USERNAME`, `EMS_PASSWORD`, `EMS_VALIDATE_CERTS` or module parameters.

## Development

Python and Ansible only import a collection from `.../ansible_collections/<namespace>/<name>`, so expose
this checkout through a symlink (kept outside the repo):

```
mkdir -p ~/collections/ansible_collections/jurajama
ln -s "$PWD" ~/collections/ansible_collections/jurajama/forticlient_ems
export ANSIBLE_COLLECTIONS_PATH=~/collections PYTHONPATH=~/collections
python3 -m pytest -p no:cacheprovider tests/unit
ansible-playbook tests/integration/m1_site_workgroup.yml   # real EMS, needs EMS_* env vars
```

The unit tests include end-to-end tests (`tests/unit/test_modules_mock_ems.py`) that run the real
modules and `EMSClient` against a simulated EMS server (`tests/mock_ems/server.py`: stdlib HTTPS
server with a throw-away self-signed certificate, needs `openssl`; sites, workgroups, async
operations, session/CSRF checks). It starts on a free port per test, so no real EMS is needed.
`tests/unit/test_playbook_mock_ems.py` also runs the integration playbook against it (the playbook
reads an optional `EMS_PORT`). To poke at it by hand: `python3 tests/mock_ems/server.py 8443` (login `admin` / `admin`).

`ansible-test` does not follow symlinks; run sanity from a copy:

```
mkdir -p /tmp/ac/ansible_collections/jurajama && cp -r . /tmp/ac/ansible_collections/jurajama/forticlient_ems
(cd /tmp/ac/ansible_collections/jurajama/forticlient_ems && ansible-test sanity --python 3.12)
```

The GitHub workflow `.github/workflows/tests.yml` runs these tests (including the mock EMS ones) on every push to `main` and on pull requests.
