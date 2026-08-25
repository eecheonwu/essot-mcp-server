# EIP MCP Server

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP Transport](https://img.shields.io/badge/mcp-stdio%20%7C%20http-green.svg)](https://modelcontextprotocol.io/)
[![Framework](https://img.shields.io/badge/framework-FastMCP-purple.svg)](https://github.com/jlowin/fastmcp)

The **EIP MCP Server** is the bridge between your local development environment and the **Engineering Intelligence Platform (EIP)**. It exposes local workspace orchestration capabilities to your AI-powered IDEs via the Model Context Protocol (MCP).

---

## 🚀 About the Engineering Intelligence Platform (EIP)

The **Engineering Intelligence Platform (EIP)** is a modern governance and planning workspace designed for AI-driven software engineering. EIP automatically maintains a Single Source of Truth (SSOT), visualizes architectural knowledge graphs, and governs architectural drift.

The **EIP MCP Server** empowers AI Coding Agents (such as Antigravity, Claude Desktop, Cursor, or Windsurf) to natively interact with your EIP project.

### How it Connects to EIP

This MCP server operates in a **dual-mode architecture**:

1. **Stdio MCP Interface**: Seamlessly exposes AI tools to your local IDE Agent, allowing it to pull architecture guidelines, parse SSOT requirements, and automatically synchronize your code drift with the remote EIP Knowledge Graph.
2. **Background Webhook Listener**: Upon initialization, the server silently spawns an HTTP listener on port `8123`. This allows the cloud-based **EIP Web App** to trigger deep architectural tasks (like generating an Implementation Plan) which are then executed securely on your local file system.

---

## 🛠️ Available Tools

When connected to your IDE, the AI agent gains access to the following tools:

- `initialize_local_ssot`: Connects to the EIP Web App to scaffold your local `ssot/` directory using the project's Software Requirements Document (SRD).
- `generate_implementation_plan`: Acts as a Staff Architect. Analyzes local SSOT context and outputs an exhaustive, step-by-step implementation plan (with embedded security architecture).
- `generate_task_plan`: Decompiles the implementation plan into highly specific executable tasks for local agents (including integrated security guardrails).
- `generate_test_plan`: Creates comprehensive testing strategies (STQE, RTM) mapped to feature requirements.
- `synchronize_ssot`: Pushes local documentation and architectural updates back to the EIP Web App's Knowledge Graph to resolve drift.

---

## 📦 Installation & Usage

You can run the EIP MCP Server either by cloning it locally or by running it remotely directly from GitHub using `uv`.

### Option A: Local Installation (Recommended)

For the best development experience and to keep your API keys secure, we recommend cloning the repository locally.

1. **Clone the Repository:**

```bash
git clone https://github.com/eecheonwu/eip-mcp-server.git
cd eip-mcp-server
```

1. **IDE Configuration:**

Add the following to your IDE's MCP configuration file (e.g., `mcp_config.json` or `claude_desktop_config.json`). Update the `--directory` path to match where you cloned the repository.

```json
{
  "mcpServers": {
    "eip-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/local/eip-mcp-server",
        "python",
        "eip_mcp_server/server.py"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here"
      }
    }
  }
}
```

### Option B: Remote Execution (No Cloning Required)

You can run the MCP server directly from the remote GitHub repository using `uv`'s ability to run code from Git URLs.

**1. Full Features (Includes Webhook Listener)**

To ensure the background webhook listener on port `8123` starts properly, you must run the server as a module. This allows inbound remote triggers from the EIP Web App.

```json
{
  "mcpServers": {
    "eip-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "git+https://github.com/eecheonwu/eip-mcp-server.git",
        "-m",
        "eip_mcp_server.server"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here"
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
    "eip-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/eecheonwu/eip-mcp-server.git",
        "eip-mcp-server"
      ],
      "env": {
        "OPENROUTER_API_KEY": "your-openrouter-api-key-here"
      }
    }
  }
}
```

> **⚠️ Warning on disabling the webhook:** Without the webhook listener, the EIP Web App cannot remotely trigger local code generation or automatically scaffold your local workspace. The integration becomes one-directional (outbound only).


### Supported IDEs

- **Claude Desktop**: Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- **Antigravity CLI / IDE**: Add to `~/.gemini/config/mcp_config.json`.
- **Cursor**: Configure via Settings > Features > MCP.

---

## 🌐 Connecting to a Cloud-Hosted EIP Web App

If your EIP Web App is hosted in the cloud (e.g., DigitalOcean, AWS), you must configure networking in both directions:

1. **Inbound (Cloud ➡️ Local Laptop):**
   The cloud-hosted EIP Web App cannot natively send webhook requests to your laptop's local port `8123` due to firewalls/NAT.
   To fix this, you must run a secure tunnel like **ngrok** (`ngrok http 8123`) or **Cloudflare Tunnels** on your local machine. You then configure the EIP Web App to send webhook triggers to the public URL provided by the tunnel.

2. **Outbound (Local Laptop ➡️ Cloud):**
   By default, the MCP server points to `http://localhost:8000` for the Web App backend. You will need to edit `server.py` and `listener.py` to replace the `localhost` URL with your cloud domain name (or refactor it to read from an environment variable) so your local tools can successfully push data back to the cloud.

---

## 🔧 Architecture Requirements

- **Python**: `3.10` or higher
- **Package Manager**: [uv](https://github.com/astral-sh/uv) by Astral
- **Ports**: Port `8123` must be available for the EIP Webhook Listener.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](../../issues).
