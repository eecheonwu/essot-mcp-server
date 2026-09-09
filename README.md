# ESSOT MCP Server

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP Transport](https://img.shields.io/badge/mcp-stdio%20%7C%20http-green.svg)](https://modelcontextprotocol.io/)
[![Framework](https://img.shields.io/badge/framework-FastMCP-purple.svg)](https://github.com/jlowin/fastmcp)

The **ESSOT MCP Server** is the bridge between your local development environment and the **Engineering SSOT Platform (ESSOT)**. It exposes local workspace orchestration capabilities to your AI-powered IDEs via the Model Context Protocol (MCP).

---

## 🚀 About the Engineering SSOT Platform (ESSOT)

The **Engineering SSOT Platform (ESSOT)** is a modern governance and planning workspace designed for AI-driven software engineering. ESSOT automatically maintains a Single Source of Truth (SSOT), visualizes architectural knowledge graphs, and governs architectural drift.

The **ESSOT MCP Server** empowers AI Coding Agents (such as Antigravity, Claude Desktop, Cursor, or Windsurf) to natively interact with your ESSOT project.

### How it Connects to ESSOT

This MCP server operates in a **dual-mode architecture**:

1. **Stdio MCP Interface**: Seamlessly exposes AI tools to your local IDE Agent, allowing it to pull architecture guidelines, parse SSOT requirements, and automatically synchronize your code drift with the remote ESSOT Knowledge Graph.
2. **Background Webhook Listener**: Upon initialization, the server silently spawns an HTTP listener on port `8123`. This allows the cloud-based **ESSOT Web App** to trigger deep architectural tasks (like generating an Implementation Plan) which are then executed securely on your local file system.

---

## 🛠️ Available Tools

When connected to your IDE, the AI agent gains access to the following tools:

- `initialize_local_ssot`: Connects to the ESSOT Web App to scaffold your local `ssot/` directory using the project's Software Requirements Document (SRD).
- `generate_implementation_plan`: Acts as a Staff Architect. Analyzes local SSOT context and outputs an exhaustive, step-by-step implementation plan (with embedded security architecture).
- `generate_task_plan`: Decompiles the implementation plan into highly specific executable tasks for local agents (including integrated security guardrails).
- `generate_test_plan`: Creates comprehensive testing strategies (STQE, RTM) mapped to feature requirements.
- `synchronize_ssot`: Pushes local documentation and architectural updates back to the ESSOT Web App's Knowledge Graph to resolve drift.

---

## 📦 Installation & Usage

You can run the ESSOT MCP Server either by cloning it locally or by running it remotely directly from GitHub using `uv`.

### Option A: Local Installation (Recommended)

For the best development experience and to keep your API keys secure, we recommend cloning the repository locally.

1. **Clone the Repository:**

```bash
git clone https://github.com/eecheonwu/essot-mcp-server.git
cd essot-mcp-server
```

1. **IDE Configuration:**

Add the following to your IDE's MCP configuration file (e.g., `mcp_config.json` or `claude_desktop_config.json`). Update the `--directory` path to match where you cloned the repository.

```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/local/essot-mcp-server",
        "python",
        "essot_mcp_server/server.py"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

### Option B: Remote Execution (No Cloning Required)

You can run the MCP server directly from the remote GitHub repository using `uv`'s ability to run code from Git URLs.

**1. Full Features (Includes Webhook Listener)**

To ensure the background webhook listener on port `8123` starts properly, you must run the server as a module. This allows inbound remote triggers from the ESSOT Web App.

```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "git+https://github.com/eecheonwu/essot-mcp-server.git",
        "-m",
        "essot_mcp_server.server"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

**2. MCP Tools Only (No Webhook Listener)**

If you only want the MCP tools (outbound capabilities) and *do not* need the background webhook listener, you can use the built-in script entry point with `uvx`:

```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/eecheonwu/essot-mcp-server.git",
        "essot-mcp-server"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

> **⚠️ Warning on disabling the webhook:** Without the webhook listener, the ESSOT Web App cannot remotely trigger local code generation or automatically scaffold your local workspace. The integration becomes one-directional (outbound only).

### Supported IDEs

- **Claude Desktop**: Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- **Antigravity CLI / IDE**: Add to `~/.gemini/config/mcp_config.json`.
- **Cursor**: Configure via Settings > Features > MCP.
- **VSCode**: Add to `.vscode/mcp_config.json`.

---

## 🌐 Connecting to a Cloud-Hosted ESSOT Web App

If your ESSOT Web App is hosted in the cloud (e.g., DigitalOcean, AWS), you must configure networking in both directions:

1. **Inbound (Cloud ➡️ Local Laptop):**
   The cloud-hosted ESSOT Web App cannot natively send webhook requests to your laptop's local port `8123` due to firewalls/NAT.
   To fix this, you must run a secure tunnel like **ngrok** (`ngrok http 8123`) or **Cloudflare Tunnels** on your local machine. You then configure the ESSOT Web App to send webhook triggers to the public URL provided by the tunnel.

2. **Outbound (Local Laptop ➡️ Cloud):**
   By default, the MCP server points to `https://essot.space` for the Web App backend. Do not Change. Provide authentication by setting the ESSOT API KEY  environment variable:

   - `ESSOT_API_KEY` (Your secure API key for the cloud backend)

---

## 🔧 Architecture Requirements

- **Python**: `3.10` or higher
- **Package Manager**: [uv](https://github.com/astral-sh/uv) by Astral
- **Ports**: Port `8123` must be available for the ESSOT Webhook Listener.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](../../issues).
