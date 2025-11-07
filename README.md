# RISU Insights MCP Server

RISU Insights is an MCP server that exposes RISU diagnostics and Ansible remediation playbooks.

## Quick Setup Using `deploy.sh`

The `ansible-ollama_mcphost` repo already ships with this server under `mcp_servers/risu-insights`, so the fastest path is:

1. (Optional) Refresh the server sources:

```bash
cd /path/to/ansible-ollama_mcphost/mcp_servers
git clone https://github.com/Spectro34/risu-insights.git risu-insights   # skip if already present
```

2. Set up the Python environment the server expects:

```bash
cd risu-insights
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Deploy from the role root with `deploy.sh`, explicitly listing this server:

```bash
cd /path/to/ansible-ollama_mcphost
./deploy.sh --servers risu-insights
```

Add GPU support (optional):

```bash
./deploy.sh --servers risu-insights --enable-gpu --gpu-runtime rocm
```

Need to combine with other MCP servers? Pass a comma-separated list:

```bash
./deploy.sh --servers filesystem,bash-commands,risu-insights
```

Prefer a playbook run instead of the wrapper? The equivalent command is:

```bash
ansible-playbook examples/risu-insights.yml
```

### 4. Verify the Setup

```bash
mcphost
```

You should see the RISU Insights tools loaded. Try asking the model to run RISU diagnostics or create remediation playbooks.

## Manual Configuration

If you prefer to configure manually, the `config.yml` file in this directory shows the required configuration:

```yaml
risu-insights:
  type: "local"
  command: ["./run-server.sh"]
  cwd: "{{ server_dir }}"
  environment:
    RISU_INSIGHTS_ROOT: "{{ server_dir }}"
    RISU_INSIGHTS_INVENTORY: "{{ server_dir }}/inventory/hosts"
    RISU_VENV: "{{ server_dir }}/.venv"
  description: "RISU Insights MCP server - exposes RISU diagnostics and Ansible remediation playbooks"
```

**Note:** The role automatically:
- Converts relative paths to absolute paths
- Adds `/bin/bash` interpreter for shell scripts
- Validates that the script exists
- Sets up the correct working directory and environment variables

## Troubleshooting

### "broken pipe" or "initialization timeout" Error

This usually means the virtual environment is missing. Make sure you've completed step 2 above:

```bash
cd mcp_servers/risu-insights
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### "executable file not found" Error

The role validates that the script exists. If you see this error, check that:
- The `run-server.sh` file exists in the `risu-insights` directory
- The file is executable: `chmod +x run-server.sh`

### Server Not Loading Tools

If `mcphost` starts but shows "Loaded 0 tools":
- Check that the virtual environment is set up correctly
- Verify that all dependencies are installed: `pip install -r requirements.txt`
- Check the server logs for errors

## Configuration Details

The role automatically handles:
- **Path Resolution**: Converts `./run-server.sh` to absolute path
- **Interpreter**: Adds `/bin/bash` for shell scripts
- **Working Directory**: Sets `cwd` to the server directory
- **Environment Variables**: Configures `RISU_INSIGHTS_ROOT`, `RISU_INSIGHTS_INVENTORY`, and `RISU_VENV`

## More Information

- RISU Insights Repository: https://github.com/Spectro34/risu-insights
- Role Documentation: [../../README.md](../../README.md)
- MCP Servers Guide: [../README.md](../README.md)
