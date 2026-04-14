# Ansible deploy (optional)

A thin wrapper around `bootstrap.sh` + `deploy.sh` for operators who
prefer a single `ansible-playbook` invocation over SSH + scp.

## Requirements

- Ansible 2.14+
- `community.general` + `ansible.posix` collections (for `synchronize`):
  ```bash
  ansible-galaxy collection install community.general ansible.posix
  ```
- Either key-based SSH to `empcloud-development@voyagent.globusdemos.com`,
  or willingness to type the password via `--ask-pass`.

## Run it

```bash
cd infra/deploy/ansible

# First time (installs Docker, creates /opt/voyagent, then deploys):
ansible-playbook -i inventory.ini playbook.yml --ask-pass --ask-become-pass

# Subsequent runs: same command. bootstrap.sh is idempotent.
```

Before the first run you must SSH in once and populate
`/opt/voyagent/.env.prod` by hand — the playbook will **abort** if
`POSTGRES_PASSWORD` or `VOYAGENT_KMS_KEY` still contain `change-me` or
are empty. The `.env.prod.example` template lives in
`infra/deploy/.env.prod.example`.

## What the playbook does

1. Copies `bootstrap.sh` to the host and runs it (idempotent).
2. rsyncs the repo to `/opt/voyagent/repo` (excluding `.git`,
   `node_modules`, `.venv`, secrets, build artifacts).
3. Ensures `/opt/voyagent/.env.prod` exists and is at least minimally
   filled.
4. Runs `deploy.sh --no-pull` as the `voyagent` user and surfaces the
   last 10 lines of output.

## Secrets

`.env.prod` never leaves the host. The playbook does **not** push
secrets from the control machine. If you want to template secrets via
ansible-vault, extend the `Ensure .env.prod exists` task to copy a
vault-encrypted file instead of the empty skeleton — but the default
expectation is that secrets are curated on the host directly.
