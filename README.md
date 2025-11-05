# RISU Insights MCP Server

RISU Insights exposes RISU diagnostics and Ansible remediation playbooks through
the Model Context Protocol (MCP). Connect any MCP-aware client (e.g. mcphost) to
drive end-to-end health checks and fixes from structured tool responses.

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
staging area even on sandboxed hosts.

## Repository Layout

```
risu_insights/            Core modules (config, diagnostics, inventory, playbooks)
worker_playbooks/         Ansible playbooks invoked by the MCP tools
remediation_playbooks/    Ready-to-run remediation examples
deploy-ollama-mcphost.yml Playbook wrapper for the shared role
deploy-qwen.yml           GPU-centric example (Qwen + Ansible Runner MCP)
```

The Ollama + mcphost role lives in a separate repository:

```
git clone https://github.com/Spectro34/ansible-ollama_mcphost.git \
  ~/.ansible/roles/ansible-ollama_mcphost
```

The RISU package can be found here: 

```
zypper addrepo https://download.opensuse.org/repositories/home:hsharma/openSUSE_Factory/home:hsharma.repo
zypper refresh
zypper install risu
```

It supports both installation and cleanup workflows. To enable GPU offload,
set `ollama_gpu_enabled: true`; to remove everything, rerun with
`ollama_state: absent` and `mcphost_state: absent`.
