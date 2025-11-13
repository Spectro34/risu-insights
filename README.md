# RISU Diagnostics MCP Server

A simple MCP server that runs RISU diagnostics and exposes the results via Model Context Protocol for use with OpenWebUI and other MCP clients.

## How It Works

The server executes RISU through Ansible for all hosts (including localhost):

**For all hosts (localhost and remote):**
- Uses Ansible command (`ansible -m shell`) to connect and execute RISU # to-do use risu ansible module
- Leverages Ansible's connection system (local, SSH, paramiko, etc.) automatically
- For localhost, uses `ansible_connection=local` from inventory
- Retrieves the JSON output from Ansible's command output
- Parses and returns the results

**Inventory:**
- Uses Ansible-style inventory files (INI format) to resolve hostnames
- Reads Ansible-style variables (ansible_user, ansible_port, ansible_become, ansible_connection, etc.) from inventory
- Passes these variables to Ansible command, which handles all connection details

The MCP server exposes two tools:
- `show_inventory` - Reads and displays the Ansible-style inventory file
- `run_diagnostics` - Executes RISU, parses results, and returns formatted reports

## Installation

```bash
cd risu-insights
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Starting the Server

```bash
risu-insights-http --inventory /path/to/inventory --host 0.0.0.0 --port 8080
```

## Ensure risu is installed on the managed nodes 

```bash
zypper addrepo https://download.opensuse.org/repositories/home:hsharma/openSUSE_Factory/home:hsharma.repo
zypper refresh
zypper install risu
```

**Inventory Path:**
- Use `--inventory /path/to/inventory` to specify a custom inventory file when starting the server
- Default inventory path: `./inventory/hosts` (relative to project root) if not specified
- You can also override the inventory path per tool call using the `inventory` parameter

**Inventory Path Resolution (priority order):**
1. Path specified in tool call (`inventory` parameter)
2. `--inventory` CLI option when starting server
3. `RISU_DIAG_INVENTORY` environment variable
4. Default `./inventory/hosts` (relative to project root)

The server exposes:
- `/mcp` - MCP streamable HTTP endpoint (for OpenWebUI)
- `/sse` - Server-Sent Events endpoint
- `/healthz` - Health check endpoint

## Adding to OpenWebUI

1. Start the RISU diagnostics server (see above)

2. In OpenWebUI, go to **Settings → Tools → Tool Servers**

3. Click **Add Server** and configure:
   - **Type**: `mcp`
   - **URL**: `http://localhost:8080/mcp` (adjust host/port if needed)
   - **OpenAPI Spec**: `openapi.json` (or leave empty)
   - **Auth**: `None`

4. Click **Verify** to test the connection

5. Save the server configuration

6. In any chat, enable the tool and use:
   - `show_inventory` - View available hosts
   - `run_diagnostics` - Run RISU diagnostics on specified hosts with optional plugin filters

## Usage Examples

- Run diagnostics on localhost: `run_diagnostics(hosts="localhost")`
- Run with plugin filter: `run_diagnostics(hosts="localhost", plugin_filter="core")`
- Run on multiple hosts: `run_diagnostics(hosts="host1,host2")`
- Run on all hosts: `run_diagnostics(hosts="all")`
- Use custom inventory: `run_diagnostics(hosts="localhost", inventory="/path/to/custom/inventory")`
- Show inventory from custom path: `show_inventory(inventory="/path/to/custom/inventory")`
