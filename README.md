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
        // Optional if using ESSOT Web App PKCE:
        // "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

### Option B: Remote Execution (No Cloning Required)

You can run the MCP server directly from the remote GitHub repository using `uv`'s ability to run code from Git URLs.

**1. Full Features (Includes Outbound Worker Tunnel)**

To ensure the background outbound worker starts properly, you must run the server as a module. This establishes the permanent encrypted tunnel with ESSOT Cloud:

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
        // Optional if using ESSOT Web App PKCE:
        // "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

**2. MCP Tools Only (Standalone Stdio Mode)**

If you only want the local IDE tools and do not wish to run the background worker tunnel:

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
        // Optional if using ESSOT Web App PKCE:
        // "OPENROUTER_API_KEY": "your-openrouter-api-key-here",
        "ESSOT_API_URL": "https://essot.space",
        "ESSOT_API_KEY": "your-essot-api-key-here"
      }
    }
  }
}
```

> **💡 Tip:** Both configurations automatically start the background outbound worker tunnel whenever your IDE launches the server, seamlessly bridging tasks with ESSOT Cloud.

### Supported IDEs

- **Claude Desktop**: Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- **Antigravity CLI / IDE**: Add to `~/.gemini/config/mcp_config.json`.
- **Cursor**: Configure via Settings > Features > MCP.
- **VSCode**: Add to `.vscode/mcp_config.json`.

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
         "command": "uv",
         "args": [
           "run",
           "--with",
           "git+https://github.com/eecheonwu/essot-mcp-server.git",
           "-m",
           "essot_mcp_server.server"
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
