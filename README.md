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

For the best development experience and to keep your API keys secure, we recommend cloning the repository locally and configuring your IDE to run it directly.

### 1. Clone the Repository

Clone this repository into a convenient directory on your local machine:

```bash
git clone https://github.com/eecheonwu/eip-mcp-server.git
cd eip-mcp-server
```

### 2. IDE Configuration (Claude Desktop, Antigravity, etc.)

To give your AI coding assistant full access to the EIP ecosystem, add the following to your IDE's MCP configuration file (e.g., `mcp_config.json` or `claude_desktop_config.json`).

While you can use a local `.env` file (see `.env.example`), the most secure strategy is to let your IDE securely inject the API keys as environment variables when it starts the server. Update the `cwd` or `--directory` path to match where you cloned the repository.

You can configure your AI model (via OpenRouter), aligning your local MCP server with the EIP Web App's AI engine.

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

> **💡 Note on Webhooks:** When your IDE starts the MCP Server, it will automatically spawn the background HTTP webhook listener on port `8123`.

#### Supported IDEs

- **Claude Desktop**: Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- **Antigravity CLI / IDE**: Add to `~/.gemini/config/mcp_config.json`.
- **Cursor**: Configure via Settings > Features > MCP.

---

## 🔧 Architecture Requirements

- **Python**: `3.10` or higher
- **Package Manager**: [uv](https://github.com/astral-sh/uv) by Astral
- **Ports**: Port `8123` must be available for the EIP Webhook Listener.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](../../issues).
