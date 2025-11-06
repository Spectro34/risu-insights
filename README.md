# WIP:RISU Insights MCP Server

RISU Insights exposes RISU diagnostics and Ansible remediation playbooks through
the Model Context Protocol (MCP). Connect any MCP-aware client (e.g. mcphost) to
drive health checks and fixes from structured tool responses. The
project expects the sibling repositories `ansible-ollama_mcphost` (role) and
`ansible-risu` (custom module) to live next to this directory so Ansible can
locate them automatically.

See [QUICKSTART.md](./QUICKSTART.md) for installation and deployment details.

## How it Works

1. **Client request** – An MCP client calls a tool such as `run_diagnostics`.
2. **Server orchestration** – `server.py` resolves hosts, renders inventory
   variables, and invokes `worker_playbooks/run-diagnostics.yml` via
   `ansible-runner`.
3. **RISU execution** – Managed nodes run RISU, returning structured JSON
   payloads that the server trims to concise per-host summaries.
4. **Remediation** – When asked, `risu_insights/playbooks.py` executes the
   selected remedy from `remediation_playbooks/`, streaming aggregated stats
   back to the client.

## Tool Surface

| Tool            | Purpose                                                         |
|-----------------|-----------------------------------------------------------------|
| `list_inventory`| Parse `inventory/hosts` and report hosts/groups                 |
| `resolve_hosts` | Expand patterns or groups without shelling out to `ansible`    |
| `run_diagnostics` | Run RISU on local or remote hosts, returning structured issues |
| `list_playbooks`| Enumerate remediation playbooks in `remediation_playbooks/`     |
| `run_playbook`  | Execute a remediation playbook and report per-host stats        |

Worker playbooks (`worker_playbooks/`) remain part of the runtime they are how
the server interacts with RISU and remote nodes.

The `tmp/ansible` directory is kept intentionally so Ansible has a writable
staging area even on sandboxed hosts. The `ansible.cfg` file points to the
bundled role (`../ansible-ollama_mcphost`) and module library
(`../ansible-risu/library`). Adjust those paths if you relocate the repositories
or export `ANSIBLE_ROLES_PATH` / `ANSIBLE_LIBRARY`.

## Repository Layout

```
risu_insights/            Core modules (config, diagnostics, inventory, playbooks)
worker_playbooks/         Ansible playbooks invoked by the MCP tools
remediation_playbooks/    Ready-to-run remediation examples
deploy-ollama-mcphost.yml Playbook wrapper for the shared role
deploy-qwen.yml           GPU-centric example (Qwen + Ansible Runner MCP)
```

## Deploying mcphost + Ollama

`deploy-ollama-mcphost.yml` wraps the shared role stored in
`../ansible-ollama_mcphost`. By default it:

- pulls the `qwen3-coder:30b` model
- enables GPU offload with the ROCm runtime (AMD)
- writes a ready-to-use `mcphost` config pointing at the RISU Insights MCP
  endpoint and registers a local `risu-insights` server that runs
  `./run-server.sh` on demand

Override variables at run-time to pick a different model or disable GPU:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit ollama-host \
  -e ollama_model=mistral:7b \
  -e ollama_pull_models='["mistral:7b"]' \
  -e ollama_gpu_enabled=false
```

If `mcphost` runs on a different machine than the RISU Insights checkout,
override the repository and virtualenv paths so the generated `mcphost` config
knows how to launch the server:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit remote-host \
  -e risu_insights_repo_path=/opt/risu/risu-insights \
  -e risu_insights_venv_path=/opt/risu/.venv
```

To wipe the mcphost config without uninstalling packages, run the playbook with
`mcphost_state=absent -e mcphost_cleanup_package=false`, then rerun with
defaults to regenerate the configuration.

 try:

    list_inventory – confirms the localhost entry
    run_diagnostics – runs RISU on localhost via the Ansible module
    run_playbook – executes sample remediation playbooks


Re-run with `ollama_state=absent` and `mcphost_state=absent` to remove the
stack, optionally toggling `mcphost_cleanup_package` to uninstall the CLI.
<img width="1651" height="944" alt="Screenshot_2025-11-06_04-40-31" src="https://github.com/user-attachments/assets/4b8ed721-b4d1-4b69-a584-1809c0b36db5" />
<img width="1732" height="977" alt="Screenshot_2025-11-06_04-38-27" src="https://github.com/user-attachments/assets/17074764-1e5c-4472-96fc-056ba833c711" />
<img width="1853" height="960" alt="Screenshot_2025-11-06_04-38-10" src="https://github.com/user-attachments/assets/b4dffd05-0dc4-4f08-8bc8-a47c1c05893c" />
<img width="1534" height="961" alt="Screenshot_2025-11-06_04-33-35" src="https://github.com/user-attachments/assets/8252ebbe-4065-4460-9bd5-5cde79d1aa74" />


