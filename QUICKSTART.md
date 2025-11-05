# Quick Start

## 1. Clone the Repositories

```bash
mkdir -p ~/risu && cd ~/risu
git clone https://github.com/Spectro34/risu-insights.git
git clone https://github.com/Spectro34/ansible-ollama_mcphost.git
git clone https://github.com/Spectro34/ansible-risu.git
```

The projects expect to sit side-by-side exactly like the layout above.

## 2. Create a Virtual Environment

```bash
cd ~/risu/risu-insights
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Install RISU Locally

RISU must be present on the machine so diagnostics succeed:

```bash
sudo zypper addrepo \
  https://download.opensuse.org/repositories/home:hsharma/openSUSE_Factory/home:hsharma.repo
sudo zypper refresh
sudo zypper install risu
```

## 4. Bootstrap Ollama + mcphost

The inventory already contains a `localhost` group configured for a local
connection, so just limit to that host:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit localhost
```

This pulls the `qwen3-coder:30b` model, enables ROCm GPU by default, and writes
`~/.mcphost.yml`. Override settings inline when needed, e.g.:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit localhost \
  -e ollama_gpu_runtime=cuda \
  -e ollama_model=mistral:7b \
  -e ollama_pull_models='["mistral:7b"]'
```
For more options check ansible-ollama_mcphost readme.

> **Note:** The role installs both `ollama` and `mcphost` via your system
> package manager.

Re-running the playbook updates the mcphost config in-place. If you want to
clear out stale config without touching the Ollama installation, run once with:

```bash
ansible-playbook deploy-ollama-mcphost.yml \
  -i inventory/hosts --limit localhost \
  -e mcphost_state=absent -e mcphost_cleanup_package=false
```

Then rerun the standard command above to regenerate the configuration.

If sudo on your machine prompts for a password, add `--ask-become-pass` to the
playbook command.

## 5. Use mcphost

Start the client that was just configured:

```bash
mcphost
```

From there, try:

- `list_inventory` – confirms the localhost entry
- `run_diagnostics` – runs RISU on localhost via the Ansible module
- `run_playbook` – executes sample remediation playbooks
