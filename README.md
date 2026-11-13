# jurajama.forticlient_ems

Ansible collection for managing **FortiClient EMS 7.4.x** (multi-site) through its REST API.

| Module | What it does |
|--------|--------------|
| [`ems_info`](#ems_info--gather-facts--test-connectivity) | Read-only: EMS version, host name, time and (optionally) the list of sites. Handy as a connectivity test. |
| [`ems_site`](#ems_site--create-or-delete-a-site) | Create or delete a site (tenant). |
| [`ems_workgroup`](#ems_workgroup--manage-endpoint-groups) | Create or delete custom endpoint groups inside a site, including nested groups. |

All modules are idempotent, support `--check` and `--diff`, and always log out of EMS when they finish.

## Requirements

- ansible-core 2.15 or newer on the control node.
- Python `requests` on the host that runs the module (the control node, since these modules talk to the EMS API from `localhost`).
- A FortiClient EMS 7.4.x server with a **global administrator** account and HTTPS API access.

## Installation

From a checkout of this repository:

```bash
ansible-galaxy collection build
ansible-galaxy collection install jurajama-forticlient_ems-*.tar.gz
```

Or install straight from Git, e.g. in `requirements.yml`:

```yaml
collections:
  - name: https://github.com/jurajama/forticlient-ems-ansible.git
    type: git
    version: main
```

```bash
ansible-galaxy collection install -r requirements.yml
```

## Quick start

The modules call the EMS API, so run them on `localhost` (not on the EMS server as an SSH target).

1. Provide credentials through environment variables (keeps secrets out of playbooks):

   ```bash
   export EMS_SERVER=ems.example.com
   export EMS_USERNAME=admin
   export EMS_PASSWORD='s3cret'
   export EMS_VALIDATE_CERTS=false     # only for self-signed lab certificates
   ```

2. Check connectivity with an ad-hoc command:

   ```bash
   ansible localhost -m jurajama.forticlient_ems.ems_info
   ```

3. Or write a playbook:

   ```yaml
   - hosts: localhost
     gather_facts: false
     tasks:
       - name: Create a customer site
         jurajama.forticlient_ems.ems_site:
           name: customer-a

       - name: Create an endpoint group in that site
         jurajama.forticlient_ems.ems_workgroup:
           site: customer-a
           name: VPN-users
   ```

   ```bash
   ansible-playbook playbook.yml
   ```

## Connection parameters

Every module accepts the same connection parameters. Each one except `port` and `timeout` can also come from an environment variable; an explicit module parameter wins.

| Parameter | Environment variable | Default | Description |
|-----------|---------------------|---------|-------------|
| `host` | `EMS_SERVER` | – (required) | EMS host name or IP address. |
| `port` | – | `443` | HTTPS port of the EMS API. |
| `username` | `EMS_USERNAME` | – (required) | Global administrator name. |
| `password` | `EMS_PASSWORD` | – (required) | Administrator password (never logged). |
| `validate_certs` | `EMS_VALIDATE_CERTS` | `true` | Validate the EMS TLS certificate. |
| `timeout` | – | `30` | HTTP timeout in seconds. |

Rather than repeating them on every task, set them once with `module_defaults`, and keep the password in Ansible Vault:

```yaml
- hosts: localhost
  gather_facts: false
  vars_files:
    - secrets.yml            # ansible-vault encrypted, defines vault_ems_password
  module_defaults:
    jurajama.forticlient_ems.ems_info: &ems
      host: ems.example.com
      username: admin
      password: "{{ vault_ems_password }}"
    jurajama.forticlient_ems.ems_site: *ems
    jurajama.forticlient_ems.ems_workgroup: *ems
  tasks:
    - jurajama.forticlient_ems.ems_info:
```

## Module reference with examples

Full parameter documentation is always available offline:

```bash
ansible-doc jurajama.forticlient_ems.ems_site
```

### `ems_info` – gather facts / test connectivity

Read-only; never reports `changed`. Always returns `hostname`, `system_time`, `version`, `version_full`, `version_comparable` and `current_site`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gather_subset` | `[min]` | `min` is always gathered; add `sites` to also return the site list. |

```yaml
- name: Show EMS version and sites
  jurajama.forticlient_ems.ems_info:
    gather_subset: [sites]
  register: ems

- ansible.builtin.debug:
    msg: "EMS {{ ems.version }} has sites: {{ ems.sites | map(attribute='display_name') | list }}"
```

Each entry in `sites` has `id`, `name`, `display_name` and `is_default`. The built-in Global pseudo-site is not listed.

### `ems_site` – create or delete a site

Runs in the Global context. Sites are identified by their display name.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `name` | – (required) | Site display name. |
| `state` | `present` | `present` creates the site if missing; `absent` deletes it. |
| `licenses` | all `0` | Seat counts, used **only when creating**. See keys below. |
| `wait` | `true` | Wait for the asynchronous create/delete operation to finish. |
| `wait_timeout` | `300` | Seconds to wait for that operation. |

License keys: `fabric_agent`, `future_fabric_agent`, `sandbox_cloud`, `future_sandbox_cloud`, `sase`, `future_sase_user`, `edr`, `future_edr`, `forensics`, `future_forensics`, `chromebook`, `vpn_only`. Unknown keys fail the task.

Returns `id` and `site` (summary dict) when the site exists, and `op_id` when an operation ran.

```yaml
- name: Create a site with no licenses
  jurajama.forticlient_ems.ems_site:
    name: customer-a

- name: Create a site with seat counts
  jurajama.forticlient_ems.ems_site:
    name: customer-b
    licenses:
      fabric_agent: 100
      vpn_only: 50
  register: site

- ansible.builtin.debug:
    msg: "Site id is {{ site.id }}"

- name: Start creating a site without waiting for it to finish
  jurajama.forticlient_ems.ems_site:
    name: customer-c
    wait: false

- name: Delete a site (this destroys ALL data in it)
  jurajama.forticlient_ems.ems_site:
    name: customer-a
    state: absent
```

Things to know:

- **Deleting a site destroys all of its data.** Try it with `--check` first.
- The `Default` and Global sites can never be deleted; the module refuses.
- Updating an existing site (rename, licenses) is not supported. If the site already exists, `licenses` is ignored with a warning and the task reports `ok`.

### `ems_workgroup` – manage endpoint groups

Creates or deletes custom endpoint groups (workgroups) in a given site. A group is identified by its full path, e.g. `All Groups/VPN-users/Laptops`. Renaming or moving groups is not supported.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `site` | – (required) | Display name of the site to work in (use `Default` for the default site). |
| `name` | – (required) | Group name; must not contain `/`. |
| `parent` | `All Groups` | Full path of the parent group. It must already exist. |
| `state` | `present` | `present` creates the group; `absent` deletes it. |
| `force` | `false` | With `state: absent`, attempt deletion even if the group has devices or an assigned policy. |

Returns `workgroup` with `id`, `guid`, `name`, `full_path`, `parent_id`, `type`, `policy_id`, `policy_name` and `total_devices`.

```yaml
- name: Top-level group
  jurajama.forticlient_ems.ems_workgroup:
    site: customer-a
    name: VPN-users

- name: Nested group (the parent must exist first)
  jurajama.forticlient_ems.ems_workgroup:
    site: customer-a
    name: Laptops
    parent: All Groups/VPN-users

- name: Remove a group, children first
  jurajama.forticlient_ems.ems_workgroup:
    site: customer-a
    name: Laptops
    parent: All Groups/VPN-users
    state: absent
```

Things to know:

- Create parents before children, and delete children before parents.
- Deleting a group that has devices or a policy assigned fails unless `force: true`.
- Built-in groups (such as `Other Endpoints`) cannot be deleted. Asking for one with `state: present` is a no-op.
- An unknown `site` or `parent` fails with a message listing what is available.

## Complete example

Provision several sites, each with a standard set of groups:

```yaml
- name: Provision EMS customer sites
  hosts: localhost
  gather_facts: false
  vars:
    customers:
      - { name: customer-a, seats: 100 }
      - { name: customer-b, seats: 250 }
    groups:
      - { name: Employees }
      - { name: Contractors }
      - { name: Laptops, parent: All Groups/Employees }
  tasks:
    - name: Sites
      jurajama.forticlient_ems.ems_site:
        name: "{{ item.name }}"
        licenses:
          fabric_agent: "{{ item.seats }}"
      loop: "{{ customers }}"

    - name: Groups in every site
      jurajama.forticlient_ems.ems_workgroup:
        site: "{{ item.0.name }}"
        name: "{{ item.1.name }}"
        parent: "{{ item.1.parent | default('All Groups') }}"
      loop: "{{ customers | product(groups) | list }}"
      loop_control:
        label: "{{ item.0.name }}: {{ item.1.name }}"
```

Groups are created in list order, so parents come before their children. Running the playbook again reports no changes.

## Check mode and diff

Preview what would change without touching EMS:

```bash
ansible-playbook playbook.yml --check --diff
```

## Return values and error handling

Failed tasks include `msg` plus, for API errors, `ems_message` (the EMS error text) and `http_status`. To handle failures in a playbook:

```yaml
- jurajama.forticlient_ems.ems_workgroup:
    site: customer-a
    name: x
    parent: does-not-exist
  register: result
  ignore_errors: true

- ansible.builtin.debug:
    var: result.msg
```

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Parameter 'host' (or its EMS_* environment variable) is required` | `EMS_SERVER`, `EMS_USERNAME` or `EMS_PASSWORD` not set. |
| TLS/certificate verification error | Self-signed EMS certificate: install the CA, or set `validate_certs: false` (lab only). |
| `Unknown site '...'. Available sites: ...` | Site name is wrong; names are display names and case-sensitive. |
| `Parent group '...' not found` | Create the parent first and give its **full path** (`All Groups/...`). |
| Missing `requests` library error | `pip install requests` for the Python used by Ansible. |

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
