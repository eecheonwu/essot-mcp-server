import os
import sys
import re
import json
import logging
import datetime
from pathlib import Path
from typing import Optional

# Ensure repository root is in sys.path for direct execution or standalone scripts
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    try:
        from fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server import FastMCP

import httpx
import requests

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("essot_mcp_server")

mcp = FastMCP("essot-mcp-server")


def get_project_root(project_path: Optional[str] = None) -> Path:
    """Resolves the project root path."""
    if project_path:
        return Path(project_path).resolve()
    if "PROJECT_ROOT" in os.environ:
        return Path(os.environ["PROJECT_ROOT"]).resolve()
    return Path(os.getcwd()).resolve()


def get_knowledge_dir(project_path: Optional[str] = None) -> Path:
    """Resolves the ssot directory for the given project path."""
    return get_project_root(project_path) / "ssot"


def _get_project_id(knowledge_dir: Path) -> Optional[str]:
    """Extracts project_id from ssot.yaml or fallback environment variable."""
    ssot_yaml_path = knowledge_dir / "ssot.yaml"
    if ssot_yaml_path.exists():
        content = ssot_yaml_path.read_text(encoding="utf-8")
        match = re.search(r"project_id:\s*([^\n\r]+)", content)
        if match:
            return match.group(1).strip()
    return os.environ.get("ESSOT_PROJECT_ID")


def _get_context(knowledge_dir: Path) -> str:
    """Helper to read all markdown files in the knowledge directory for agent context."""
    context_parts = []
    if knowledge_dir.exists():
        for file in knowledge_dir.rglob("*.md"):
            if "agents" in file.parts:
                continue
            context_parts.append(f"--- {file.name} ---\n{file.read_text(encoding='utf-8')}\n")
    return "\n".join(context_parts) if context_parts else "No local SSOT context found."


def _scaffold_agent_packages(knowledge_dir: Path):
    """Generates standard agent context packages based on local SSOT."""
    agents_dir = knowledge_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    context = _get_context(knowledge_dir)

    frontend_agent = (
        f"# Frontend Engineer Agent\n\n"
        f"## Role\n"
        f"You are the Frontend UI Engineer. Your job is to implement the user interface based on `implementation-plan.md`, `task-plan.md`, and the SSOT.\n\n"
        f"## Context\n{context}"
    )
    backend_agent = (
        f"# Backend Engineer Agent\n\n"
        f"## Role\n"
        f"You are the Backend API Engineer. Your job is to implement the server logic, database models, and APIs based on `implementation-plan.md`, `task-plan.md`, and the SSOT.\n\n"
        f"## Context\n{context}"
    )
    qa_agent = (
        f"# QA Testing Agent\n\n"
        f"## Role\n"
        f"You are the Test Engineer. Your job is to ensure code quality by executing and verifying `test-plan.md` against the SSOT.\n\n"
        f"## Context\n{context}"
    )

    (agents_dir / "frontend_agent.md").write_text(frontend_agent, encoding="utf-8")
    (agents_dir / "backend_agent.md").write_text(backend_agent, encoding="utf-8")
    (agents_dir / "qa_agent.md").write_text(qa_agent, encoding="utf-8")


@mcp.tool()
def initialize_local_ssot(project_id: str, project_path: Optional[str] = None) -> str:
    """
    Connects to the ESSOT Web App, pulls initial business requirements, architecture documents,
    and specifications, and scaffolds the local ssot/ directory tree.
    """
    knowledge_dir = get_knowledge_dir(project_path)
    dirs = ["requirements", "architecture", "system", "testing", "agents"]
    for d in dirs:
        dir_path = knowledge_dir / d
        dir_path.mkdir(parents=True, exist_ok=True)
        (dir_path / ".gitkeep").touch(exist_ok=True)

    essot_api_url = os.environ.get("ESSOT_API_URL", "https://essot.space").rstrip("/")
    essot_api_key = os.environ.get("ESSOT_API_KEY")

    headers = {}
    if essot_api_key:
        headers["Authorization"] = f"Bearer {essot_api_key}"

    artifacts = []
    try:
        resp = httpx.get(
            f"{essot_api_url}/api/v1/projects/{project_id}/artifacts",
            headers=headers,
            timeout=15.0
        )
        if resp.status_code == 200:
            artifacts = resp.json()
    except Exception as exc:
        logger.warning(f"Could not fetch artifacts from ESSOT Cloud: {exc}. Proceeding with local scaffolding.")

    # Materialize retrieved artifacts
    saved_count = 0
    for artifact in artifacts:
        name = artifact.get("name", "artifact")
        if not name.endswith(".md") and not name.endswith(".yaml"):
            name += ".md"

        atype = str(artifact.get("artifact_type") or "").upper()
        if atype in ("SRD", "REQUIREMENT", "REQUIREMENTS"):
            target_path = knowledge_dir / "requirements" / name
        elif atype in ("ADR", "UML", "C4", "C4_DIAGRAM", "ARCHITECTURE"):
            target_path = knowledge_dir / "architecture" / name
        elif atype in ("TEST_SPEC", "TEST SPEC", "TESTING"):
            target_path = knowledge_dir / "testing" / name
        else:
            target_path = knowledge_dir / "system" / name

        content = artifact.get("content") or ""
        target_path.write_text(content, encoding="utf-8")
        saved_count += 1

    # Fallback SRD if none fetched
    srd_path = knowledge_dir / "requirements" / "SRD.md"
    if not srd_path.exists() and saved_count == 0:
        srd_content = f"# Software Requirements Document\n\nScaffolded for project `{project_id}`.\n"
        srd_path.write_text(srd_content, encoding="utf-8")

    # Materialize ssot.yaml manifest
    ssot_yaml_path = knowledge_dir / "ssot.yaml"
    if not ssot_yaml_path.exists():
        now = datetime.datetime.now().isoformat()
        ssot_yaml_content = f"""project_id: {project_id}
version: 1.0.0
last_synced: "{now}"
description: "Local Engineering SSOT synchronized from ESSOT Web App"
directories:
  requirements: "SRDs and business requirements"
  architecture: "ADRs, C4, and UML diagrams"
  system: "Knowledge Graph and technical specifications"
  testing: "Test specifications and coverage"
  agents: "AI Agent context packages"
"""
        ssot_yaml_path.write_text(ssot_yaml_content, encoding="utf-8")

    # Generate multi-agent context packages
    _scaffold_agent_packages(knowledge_dir)

    return f"Successfully scaffolded local SSOT in {knowledge_dir} ({saved_count} artifacts synchronized from ESSOT)."


def _generate_and_save_plan(
    project_path: Optional[str],
    plan_type: str,
    filename: str,
    plan_name: str,
    provider: str = "openrouter"
) -> str:
    """
    Delegates plan generation to the backend ESSOT Planning Engine via authenticated API.
    Writes the resulting markdown plan to the workspace root.
    """
    knowledge_dir = get_knowledge_dir(project_path)
    project_id = _get_project_id(knowledge_dir)

    if not project_id:
        return (
            "Error: Cannot generate plan without a valid project_id. "
            "Please run initialize_local_ssot(project_id) first or set ESSOT_PROJECT_ID."
        )

    essot_api_url = os.environ.get("ESSOT_API_URL", "https://essot.space").rstrip("/")
    essot_api_key = os.environ.get("ESSOT_API_KEY")

    if not essot_api_key:
        return (
            "Error: ESSOT_API_KEY environment variable is not set. "
            "Please configure your ESSOT_API_KEY in your IDE MCP configuration."
        )

    headers = {
        "Authorization": f"Bearer {essot_api_key}",
        "X-AI-Provider": provider if ":" in provider else f"{provider}:anthropic/claude-3.5-sonnet",
    }
    payload = {
        "plan_type": plan_type,
        "provider": provider if ":" in provider else f"{provider}:anthropic/claude-3.5-sonnet",
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{essot_api_url}/api/v1/projects/{project_id}/plans/generate",
                json=payload,
                headers=headers,
            )
            if resp.status_code not in (200, 201):
                return f"Error: Plan generation failed on ESSOT server ({resp.status_code}): {resp.text}"

            plan_data = resp.json()
            markdown_content = plan_data.get("markdown")
            if not markdown_content:
                # Fallback if markdown field wasn't included
                plan_dict = plan_data.get("plan_data", {})
                markdown_content = json.dumps(plan_dict, indent=2) if isinstance(plan_dict, (dict, list)) else str(plan_dict)

            output_path = get_project_root(project_path) / filename
            output_path.write_text(markdown_content, encoding="utf-8")
            return f"{plan_name} generated successfully at {output_path}"
    except httpx.RequestError as exc:
        return f"Network error connecting to ESSOT Web App at {essot_api_url}: {str(exc)}"
    except Exception as exc:
        return f"Failed to generate {plan_name}: {str(exc)}"


@mcp.tool()
def generate_implementation_plan(project_path: Optional[str] = None, provider: str = "openrouter") -> str:
    """
    Connects to the ESSOT Planning Engine to synthesize an exhaustive,
    enterprise-grade Engineering Implementation Strategy (C4, data schemas, contracts).
    Saves the output directly to ./implementation-plan.md.
    """
    return _generate_and_save_plan(
        project_path=project_path,
        plan_type="Implementation Plan",
        filename="implementation-plan.md",
        plan_name="Engineering Implementation Strategy",
        provider=provider,
    )


@mcp.tool()
def generate_task_plan(project_path: Optional[str] = None, provider: str = "openrouter") -> str:
    """
    Connects to the ESSOT Planning Engine to synthesize an exhaustive,
    chronological Engineering Task Plan with dependency graph and mandatory SSOT closure.
    Saves the output directly to ./task-plan.md.
    """
    return _generate_and_save_plan(
        project_path=project_path,
        plan_type="Task Plan",
        filename="task-plan.md",
        plan_name="Engineering Task Plan",
        provider=provider,
    )


@mcp.tool()
def generate_test_plan(project_path: Optional[str] = None, provider: str = "openrouter") -> str:
    """
    Connects to the ESSOT Planning Engine to synthesize an exhaustive,
    STQE Engineering Test Plan with automated test suites and quality gates.
    Saves the output directly to ./test-plan.md.
    """
    return _generate_and_save_plan(
        project_path=project_path,
        plan_type="Test Plan",
        filename="test-plan.md",
        plan_name="Engineering Test Plan",
        provider=provider,
    )


@mcp.tool()
def synchronize_ssot(update_summary: str, project_path: Optional[str] = None) -> str:
    """
    Called by the IDE Coding Agent to synchronize local SSOT changes with the ESSOT Web App.
    Reads the local ssot/ directory, determines what has changed, and pushes the updates 
    back to the cloud database and Knowledge Graph.
    
    Args:
        update_summary: A brief description of what was changed locally during development.
    """
    logger.info(f"Triggering SSOT Orchestrator sync: {update_summary}")
    
    knowledge_dir = get_knowledge_dir(project_path)
    ssot_yaml_path = knowledge_dir / "ssot.yaml"
    project_id = _get_project_id(knowledge_dir)
            
    if not project_id:
        return "Error: Cannot sync without a valid project_id in ssot.yaml"
        
    items = []
    # Collect all markdown files from the primary knowledge directories
    for d in ["requirements", "architecture", "system", "testing"]:
        dir_path = knowledge_dir / d
        if dir_path.exists():
            for file_path in dir_path.glob("*.md"):
                if "web_graph" in file_path.name.lower() or "web graph" in file_path.name.lower():
                    continue
                
                atype = None
                if d == "requirements":
                    atype = "SRD"
                elif d == "architecture":
                    if "adr" in file_path.name.lower():
                        atype = "ADR"
                    elif "c4" in file_path.name.lower():
                        atype = "C4_DIAGRAM"
                    elif "uml" in file_path.name.lower():
                        atype = "UML"
                elif d == "testing":
                    atype = "TECHNICAL_SPEC"
                
                items.append({
                    "filename": file_path.name,
                    "content": file_path.read_text(encoding="utf-8"),
                    "artifact_type": atype
                })
                
    if not items:
        return "No markdown files found to sync."
        
    try:
        essot_api_url = os.environ.get("ESSOT_API_URL", "https://essot.space").rstrip("/")
        headers = {}
        essot_api_key = os.environ.get("ESSOT_API_KEY")
        if essot_api_key:
            headers["Authorization"] = f"Bearer {essot_api_key}"
            
        response = requests.post(
            f"{essot_api_url}/api/v1/projects/{project_id}/ssot/sync",
            json={
                "update_summary": update_summary,
                "items": items
            },
            headers=headers,
            timeout=15.0
        )
        response.raise_for_status()
        result = response.json()
        
        # Update timestamp on success
        now = datetime.datetime.now().isoformat()
        if ssot_yaml_path.exists():
            ssot_content = ssot_yaml_path.read_text(encoding="utf-8")
            ssot_content = ssot_content.replace('last_synced: ""', f'last_synced: "{now}"')
            ssot_yaml_path.write_text(ssot_content, encoding="utf-8")
        
        return f"Successfully synchronized local SSOT with ESSOT Web App. {result.get('artifacts_updated', 0)} artifacts updated. {update_summary}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Sync failed: {e}")
        return f"Error during synchronization: {e}"


def start_background_worker():
    """Starts the outbound WebSocket worker in a background daemon thread."""
    import threading
    import asyncio
    try:
        from essot_mcp_server.listener import run_outbound_websocket_worker
    except (ImportError, ModuleNotFoundError):
        from listener import run_outbound_websocket_worker

    def worker_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_outbound_websocket_worker())
        except Exception as e:
            logger.error("Outbound WebSocket worker exited: %s", e)
        finally:
            loop.close()

    t = threading.Thread(target=worker_thread, daemon=True)
    t.start()
    logger.info("🟢 Outbound WebSocket worker thread started.")


def main():
    logger.info("Starting ESSOT MCP Server...")
    start_background_worker()
    mcp.run()


if __name__ == "__main__":
    main()
