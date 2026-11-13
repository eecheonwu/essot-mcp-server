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
2. **Enterprise Outbound Worker Tunnel**: Automatically establishes an encrypted outbound WebSocket connection over standard TLS (Port 443) to the ESSOT Web App. This allows the cloud-based **ESSOT Web App** to dispatch deep architectural tasks (scaffolding SSOT, generating plans, running Forge verifications) directly to your local workspace without opening any inbound firewall ports. (An internal `127.0.0.1:8123` listener is also maintained as a fallback for offline/local development).

---

## 🛠️ Available Tools

When connected to your IDE, the AI agent gains access to the following tools:

- `initialize_local_ssot`: Connects to the ESSOT Web App to scaffold your local `ssot/` directory using the project's Software Requirements Document (SRD).
- `generate_implementation_plan`: Acts as a Staff Architect. Analyzes local SSOT context and outputs an exhaustive, step-by-step implementation plan (with embedded security architecture).
- `generate_task_plan`: Decompiles the implementation plan into highly specific executable tasks for local agents (including integrated security guardrails).
- `generate_test_plan`: Creates comprehensive testing strategies (STQE, RTM) mapped to feature requirements.
- `synchronize_ssot`: Pushes local documentation and architectural updates back to the ESSOT Web App's Knowledge Graph to resolve drift.

---

## 📦 Installation & Quickstart

No manual repository downloads or cloning required. Once published to PyPI, your AI IDE can run `essot-mcp-server` on demand using `uvx` (or `pipx`).

### 1-Step Setup (Recommended)

Add `essot-mcp-server` directly to your IDE's MCP configuration:

```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "uvx",
      "args": [
        "essot-mcp-server"
      ],
      "env": {
        "ESSOT_API_KEY": "essot_your_api_key_here"
      }
    }
  }
}
```

> **Note:** If your ESSOT instance is self-hosted or uses a custom domain, optionally set `"ESSOT_API_URL": "https://your-domain.com"`. By default, it connects to `https://essot.space`.

### Alternative Runners

#### Using pipx:
```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "pipx",
      "args": [
        "run",
        "essot-mcp-server"
      ],
      "env": {
        "ESSOT_API_KEY": "essot_your_api_key_here"
      }
    }
  }
}
```

#### Traditional pip installation:
```bash
pip install essot-mcp-server
```
```json
{
  "mcpServers": {
    "essot-mcp-server": {
      "command": "essot-mcp-server",
      "env": {
        "ESSOT_API_KEY": "essot_your_api_key_here"
      }
    }
  }
}
```

### Supported IDEs & Configuration Locations

- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- **Antigravity CLI / IDE**: `~/.gemini/config/mcp_config.json`.
- **Cursor**: Settings > Features > MCP.
- **VSCode**: `.vscode/mcp_config.json`.


---

## 🌐 Permanent Secure Outbound Worker Tunnel (Native IDE Bridge)

When connecting to the cloud-hosted ESSOT Web App (`https://essot.space`):

1. **Enterprise Security & Zero Open Ports:**
   The MCP server uses an **outbound-only WebSocket architecture** over standard encrypted TLS (Port 443). Corporate firewalls and NAT permit outbound HTTPS/WSS traffic freely. Once authenticated, a bidirectional full-duplex session is established directly with ESSOT Cloud. No public ingress ports or third-party tunnel relays are required.

2. **Native IDE Setup (1 Step):**
   Generate your `ESSOT_API_KEY` from **User Settings ⚙️** in the ESSOT Web App, and configure it directly in your IDE's MCP config:

   ```json
   {
     "mcpServers": {
       "essot-mcp-server": {
         "command": "uvx",
         "args": [
           "essot-mcp-server"
         ],
         "env": {
           "ESSOT_API_KEY": "essot_your_api_key_here"
         }
       }
     }
   }
   ```

   When your IDE opens, the server starts automatically and logs:

   ```text
   🟢 Outbound WebSocket tunnel established with ESSOT Cloud. Permanent tunnel active.
   ```

   Now, clicking **Scaffold Local SSOT** or **Generate Plan** in the Web App, or running Forge verification tests, immediately dispatches tasks to your local workspace without any terminal commands or firewall adjustments.

---

## 🔧 Architecture Requirements

- **Python**: `3.10` or higher
- **Package Manager**: [uv](https://github.com/astral-sh/uv) by Astral
- **Inbound Ports**: **Zero incoming ports required**. Remote cloud dispatch operates 100% via outbound encrypted WebSocket (TLS Port 443).

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](../../issues).
