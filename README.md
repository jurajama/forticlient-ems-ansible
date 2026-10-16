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

`ansible-test` does not follow symlinks; run sanity from a copy:

```
mkdir -p /tmp/ac/ansible_collections/jurajama && cp -r . /tmp/ac/ansible_collections/jurajama/forticlient_ems
(cd /tmp/ac/ansible_collections/jurajama/forticlient_ems && ansible-test sanity --python 3.12)
```
