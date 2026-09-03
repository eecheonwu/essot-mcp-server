import os
import sys
import logging
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from essot_mcp_server.generator.plan_generator import PlanGenerator
from essot_mcp_server.prompts.architect import ARCHITECT_PROMPT
from essot_mcp_server.prompts.developer import DEVELOPER_PROMPT
from essot_mcp_server.prompts.tester import TESTER_PROMPT

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("essot_mcp_server")

mcp = FastMCP("essot-mcp-server")

def get_project_root(project_path: str = None) -> Path:
    """Resolves the project root path."""
    if project_path:
        return Path(project_path).resolve()
    if "PROJECT_ROOT" in os.environ:
        return Path(os.environ["PROJECT_ROOT"]).resolve()
    return Path(os.getcwd()).resolve()

def get_knowledge_dir(project_path: str = None) -> Path:
    """Resolves the ssot directory for the given project path."""
    return get_project_root(project_path) / "ssot"

# Webhook listener is started explicitly in listener.py

def _get_context(knowledge_dir: Path) -> str:
    """Helper to read all markdown files in the knowledge directory for context."""
    context_parts = []
    if knowledge_dir.exists():
        for file in knowledge_dir.rglob("*.md"):
            if "agents" in file.parts:
                continue
            context_parts.append(f"--- {file.name} ---\n{file.read_text(encoding='utf-8')}\n")
    return "\n".join(context_parts) if context_parts else "No local SSOT context found."

@mcp.tool()
def initialize_local_ssot(project_id: str, project_path: str = None) -> str:
    """
    Connects to the ESSOT Web App, pulls initial business requirements (SRD)
    and scaffolds the local knowledge/ directory.
    """
    knowledge_dir = get_knowledge_dir(project_path)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    # STUB: Future API call to Web Backend
    srd_path = knowledge_dir / "SRD.md"
    srd_content = f"# Software Requirements Document\n\nScaffolded for project {project_id}."
    if not srd_path.exists():
        srd_path.write_text(srd_content, encoding='utf-8')
    
    return f"Successfully scaffolded local SSOT in {knowledge_dir}"

def _generate_and_save_plan(project_path: str | None, provider: str, system_prompt: str, filename: str, plan_name: str) -> str:
    """Helper to generate and save a markdown plan."""
    knowledge_dir = get_knowledge_dir(project_path)
    generator = PlanGenerator(provider=provider)
    context = _get_context(knowledge_dir)
    plan_content = generator.generate_markdown_plan(system_prompt=system_prompt, context=context)
    
    output_path = knowledge_dir.parent / filename
    output_path.write_text(plan_content, encoding="utf-8")
    
    return f"{plan_name} generated successfully at {output_path}"

@mcp.tool()
def generate_implementation_plan(project_path: str = None, provider: str = "openrouter") -> str:
    """
    Acts as the Software Architect. Reads local SSOT artifacts and generates
    a massive, professional-grade implementation-plan.md.
    """
    return _generate_and_save_plan(
        project_path, provider, ARCHITECT_PROMPT, "implementation-plan.md", "Implementation Plan"
    )

@mcp.tool()
def generate_task_plan(project_path: str = None, provider: str = "openrouter") -> str:
    """Generates an exhaustive Task Plan and saves it to the local workspace."""
    return _generate_and_save_plan(
        project_path, provider, DEVELOPER_PROMPT, "task-plan.md", "Task Plan"
    )

@mcp.tool()
def generate_test_plan(project_path: str = None, provider: str = "openrouter") -> str:
    """Generates an exhaustive Test Plan and saves it to the local workspace."""
    return _generate_and_save_plan(
        project_path, provider, TESTER_PROMPT, "test-plan.md", "Test Plan"
    )

@mcp.tool()
def synchronize_ssot(update_summary: str, project_path: str = None) -> str:
    """
    Called by the IDE Coding Agent to synchronize local SSOT changes with the ESSOT Web App.
    Reads the local ssot/ directory, determines what has changed, and pushes the updates 
    back to the cloud database and Knowledge Graph.
    
    Args:
        update_summary: A brief description of what was changed locally during development.
    """
    logger.info(f"Triggering SSOT Orchestrator sync: {update_summary}")
    
    import datetime
    import requests
    import re
    
    knowledge_dir = get_knowledge_dir(project_path)
    ssot_yaml_path = knowledge_dir / "ssot.yaml"
    project_id = None
    if ssot_yaml_path.exists():
        content = ssot_yaml_path.read_text(encoding="utf-8")
        match = re.search(r"project_id:\s*([^\n\r]+)", content)
        if match:
            project_id = match.group(1).strip()
            
    if not project_id:
        return "Error: Cannot sync without a valid project_id in ssot.yaml"
        
    items = []
    # Collect all markdown files from the primary knowledge directories
    for d in ["requirements", "architecture", "system", "testing"]:
        dir_path = knowledge_dir / d
        if dir_path.exists():
            for file_path in dir_path.glob("*.md"):
                # Skip the web graph artifact as it shouldn't be duplicated in the web SSOT
                if "web_graph" in file_path.name.lower() or "web graph" in file_path.name.lower():
                    continue
                
                # Infer artifact type based on folder mapping
                atype = None
                if d == "requirements": atype = "SRD"
                elif d == "architecture":
                    if "adr" in file_path.name.lower(): atype = "ADR"
                    elif "c4" in file_path.name.lower(): atype = "C4_DIAGRAM"
                    elif "uml" in file_path.name.lower(): atype = "UML"
                elif d == "testing": atype = "TECHNICAL_SPEC"
                
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
            timeout=10.0
        )
        response.raise_for_status()
        result = response.json()
        
        # Update timestamp on success
        now = datetime.datetime.now().isoformat()
        ssot_content = ssot_yaml_path.read_text(encoding="utf-8")
        ssot_content = ssot_content.replace('last_synced: ""', f'last_synced: "{now}"')
        ssot_yaml_path.write_text(ssot_content, encoding="utf-8")
        
        return f"Successfully synchronized local SSOT with ESSOT Web App. {result.get('artifacts_updated', 0)} artifacts updated. {update_summary}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Sync failed: {e}")
        return f"Error during synchronization: {e}"

if __name__ == "__main__":
    logger.info("Starting ESSOT MCP Server...")
    
    # === Start Webhook Listener in Background ===
    import threading
    import socket
    import uvicorn
    
    # Check if port is already in use
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', 8123)) != 0:
            def run_uvicorn():
                from essot_mcp_server.listener import app
                # Hide access logs to prevent polluting IDE stdout
                config = uvicorn.Config(app, host="0.0.0.0", port=8123, log_level="error")
                server = uvicorn.Server(config)
                server.run()
                
            t = threading.Thread(target=run_uvicorn, daemon=True)
            t.start()
            logger.info("Background webhook listener started on port 8123.")
        else:
            logger.info("Port 8123 is already in use. Assuming webhook listener is already running.")
    # ============================================
    
    mcp.run()
