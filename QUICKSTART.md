# Quick Start

Spin up the RISU Insights MCP server locally and (optionally) prepare an MCPHost
client with Ollama using Ansible.

## 1. Prerequisites

- Linux/macOS host with Python 3.9+
- Ansible 2.13+ (only needed for the optional deployment step)
- SSH access to any managed nodes listed in `inventory/hosts`

## 2. Install Dependencies

```bash
git clone https://github.com/<your-org>/risu-insights.git
cd risu-insights
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
The RISU package can be found here: 

```bash
zypper addrepo https://download.opensuse.org/repositories/home:hsharma/openSUSE_Factory/home:hsharma.repo
zypper refresh
zypper install risu
```

## 3. Configure Inventory (optional)

Edit `inventory/hosts` to add remote targets. Host and group variables declared
there are automatically used by the MCP server to reach managed nodes.

## 4. Run the MCP Server

```bash
./run-server.sh
```

By default the server listens on `127.0.0.1:8000`. To change the bind address or
port, set environment variables before starting:

```bash
export RISU_INSIGHTS_HOST=0.0.0.0
export RISU_INSIGHTS_PORT=9000
./run-server.sh
```

## 5. Optional: Bootstrap Ollama + MCPHost

Install the shared role so Ansible can find it (for example by cloning into your
default roles directory):

```bash
git clone https://github.com/Spectro34/ansible-ollama_mcphost.git \
  ~/.ansible/roles/ansible-ollama_mcphost
```

Then point the playbook at the host that will run `mcphost`:

```bash
ansible-playbook deploy-ollama-mcphost.yml -i inventory/hosts --limit <target>
```

Override the endpoint if the server runs elsewhere:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit <target> \
  -e risu_mcp_host=my-server.example.com \
  -e risu_mcp_port=9000
```

During installation the role leaves GPU offload disabled and does not pull any
models. Enable and customise these behaviours by setting variables:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit gpu-node \
  -e ollama_gpu_enabled=true \
  -e ollama_pull_models='["qwen2.5:32b"]'
```

To reverse the installation (stop services, drop config files, and optionally
uninstall packages) run the playbook again with `ollama_state=absent` and
`mcphost_state=absent`:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit <target> \
  -e ollama_state=absent -e mcphost_state=absent \
  -e mcphost_cleanup_package=true
```

For a GPU-focused example that also wires in the Ansible Runner MCP server, see
`deploy-qwen.yml`. Both playbooks assume the role is available on Ansible’s
standard roles path (e.g. `~/.ansible/roles/ansible-ollama_mcphost`).

Afterwards, SSH to the target and launch the client:

```bash
mcphost
```

## 6. Verifying the Flow

From any MCP client (e.g. `mcphost`), call the tools exposed by the server:

- `list_inventory` to inspect hosts/groups
- `run_diagnostics` to execute RISU on local or remote nodes
- `run_playbook` to apply remediation playbooks in `remediation_playbooks/`

All diagnostics run through `worker_playbooks/run-diagnostics.yml`, so ensure
managed nodes can reach the server over SSH and have RISU available (or use the
provided `install-risu-package.yml` helper).
