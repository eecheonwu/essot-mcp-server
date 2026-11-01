import os
import logging
import sys
import threading
from typing import List, Dict, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
import uvicorn
from pydantic import BaseModel

# Import our MCP server and patcher functions
from essot_mcp_server.server import (
    generate_implementation_plan,
    generate_task_plan,
    generate_test_plan,
    get_knowledge_dir,
    get_project_root,
)
from essot_mcp_server.patcher import (
    apply_patch_to_local_workspace,
    run_local_verification,
    read_workspace_files,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("trigger_listener")

app = FastAPI(title="ESSOT Local MCP Webhook Listener")


class TriggerPayload(BaseModel):
    project_id: str
    plan_id: Optional[str] = None
    plan_type: str
    artifacts: List[Dict] = []
    graph_context: str = ""
    project_path: Optional[str] = None
    provider: str = "openrouter"
    task_id: Optional[str] = None
    patch_id: Optional[str] = None
    diff: Optional[str] = None
    diff_hash: Optional[str] = None
    touched_files: List[str] = []
    commands: List[str] = []
    api_key: Optional[str] = None
    api_url: Optional[str] = None


plan_lock = threading.Lock()


def process_plan(payload: TriggerPayload):
    with plan_lock:
        if payload.api_key:
            os.environ["OPENROUTER_API_KEY"] = payload.api_key
        knowledge_dir = get_knowledge_dir(payload.project_path)
        logger.info(f"Received trigger to generate {payload.plan_type} in {knowledge_dir}")
        
        # Scaffold SSOT directories
        dirs = ["requirements", "architecture", "system", "testing", "agents"]
        for d in dirs:
            dir_path = knowledge_dir / d
            dir_path.mkdir(parents=True, exist_ok=True)
            (dir_path / ".gitkeep").touch(exist_ok=True)
            
        ssot_yaml_path = knowledge_dir / "ssot.yaml"
        if not ssot_yaml_path.exists():
            ssot_yaml_content = f"""project_id: {payload.project_id}
version: 1.0.0
last_synced: ""
description: "Local Engineering SSOT synchronized from ESSOT Web App"
directories:
  requirements: "SRDs and business requirements"
  architecture: "ADRs, C4, and UML diagrams"
  system: "Knowledge Graph and technical specifications"
  testing: "Test specifications and coverage"
  agents: "AI Agent context packages"
"""
            ssot_yaml_path.write_text(ssot_yaml_content, encoding='utf-8')
        
        # Map artifacts to appropriate directories
        for artifact in payload.artifacts:
            name = artifact.get("name", "artifact")
            if not name.endswith(".md"):
                name += ".md"
                
            atype = artifact.get("type", "")
            if atype == "SRD":
                target_path = knowledge_dir / "requirements" / name
            elif atype in ("ADR", "UML", "C4"):
                target_path = knowledge_dir / "architecture" / name
            elif atype in ("TEST_SPEC", "Test Spec"):
                target_path = knowledge_dir / "testing" / name
            else:
                target_path = knowledge_dir / "system" / name
                
            content = artifact.get("content")
            if content is None:
                content = ""
                
            target_path.write_text(content, encoding='utf-8')
            
        if payload.graph_context:
            (knowledge_dir / "system" / "WEB_GRAPH_CONTEXT.md").write_text(payload.graph_context, encoding='utf-8')
        
        if payload.plan_type == "Implementation Plan":
            generate_implementation_plan(project_path=payload.project_path, provider=payload.provider)
        elif payload.plan_type == "Task Plan":
            generate_task_plan(project_path=payload.project_path, provider=payload.provider)
        elif payload.plan_type == "Test Plan":
            generate_test_plan(project_path=payload.project_path, provider=payload.provider)
        elif payload.plan_type == "Local SSOT Sync":
            from essot_mcp_server.server import _get_context
            context = _get_context(knowledge_dir)
            agents_dir = knowledge_dir / "agents"
            
            frontend_agent = f"# Frontend Engineer Agent\n\n## Role\nYou are the Frontend UI Engineer. Your job is to implement the user interface based on `implementation-plan.md`, `task-plan.md`, and the SSOT.\n\n## Context\n{context}"
            backend_agent = f"# Backend Engineer Agent\n\n## Role\nYou are the Backend API Engineer. Your job is to implement the server logic, database models, and APIs based on `implementation-plan.md`, `task-plan.md`, and the SSOT.\n\n## Context\n{context}"
            qa_agent = f"# QA Testing Agent\n\n## Role\nYou are the Test Engineer. Your job is to ensure code quality by executing and verifying `test-plan.md` against the SSOT.\n\n## Context\n{context}"
            
            (agents_dir / "frontend_agent.md").write_text(frontend_agent, encoding="utf-8")
            (agents_dir / "backend_agent.md").write_text(backend_agent, encoding="utf-8")
            (agents_dir / "qa_agent.md").write_text(qa_agent, encoding="utf-8")
            logger.info("Local SSOT successfully scaffolded. Agents generated. Skipping plan generation.")
        else:
            logger.warning(f"Unknown plan type: {payload.plan_type}")
            generate_implementation_plan(project_path=payload.project_path, provider=payload.provider)
            
        if payload.plan_id:
            try:
                import httpx
                essot_api_url = (payload.api_url or os.environ.get("ESSOT_API_URL", "https://essot.space")).rstrip("/")
                headers = {}
                essot_api_key = os.environ.get("ESSOT_API_KEY")
                if essot_api_key:
                    headers["Authorization"] = f"Bearer {essot_api_key}"
                
                httpx.post(f"{essot_api_url}/api/v1/plans/{payload.plan_id}/complete", headers=headers, timeout=5.0)
                logger.info(f"Successfully notified backend of plan completion for {payload.plan_id} at {essot_api_url}")
            except Exception as e:
                logger.error(f"Failed to notify backend of plan completion: {e}")


@app.post("/trigger")
async def trigger_webhook(payload: TriggerPayload, background_tasks: BackgroundTasks):
    """Webhook listener that kicks off local SSOT generation, patch applications, or verification checks."""
    logger.info(f"Webhook hit for project {payload.project_id}: {payload.plan_type}")

    # Synchronous inspection / reading of workspace files (used by remote patch generators)
    if payload.plan_type in ("Read Files", "Get Files", "File Content", "Inspect Files"):
        target_path = payload.project_path or os.getcwd()
        logger.info(f"Reading workspace files from '{target_path}': {payload.touched_files}")
        try:
            files_data = read_workspace_files(
                workspace_root=target_path,
                files=payload.touched_files or [],
            )
            return {
                "status": "success",
                "files": files_data,
            }
        except Exception as exc:
            logger.error(f"Failed to read workspace files: {exc}")
            raise HTTPException(status_code=400, detail=str(exc))

    # Synchronous patch application (executes in milliseconds on local workspace files)
    elif payload.plan_type in ("Apply Patch", "Patch", "Forge Patch"):
        target_path = payload.project_path or os.getcwd()
        logger.info(f"Applying patch to local workspace '{target_path}'")
        try:
            applied_files = apply_patch_to_local_workspace(
                workspace_root=target_path,
                diff=payload.diff or "",
                touched_files=payload.touched_files or None,
            )
            return {
                "status": "success",
                "message": f"Successfully applied patch to {len(applied_files)} files in {target_path}",
                "applied_files": applied_files,
            }
        except Exception as exc:
            logger.error(f"Failed to apply patch: {exc}")
            raise HTTPException(status_code=400, detail=str(exc))

    # Synchronous deterministic verification execution (pytest, ruff, etc.)
    elif payload.plan_type in ("Verify Patch", "Run Verification", "Verification"):
        target_path = payload.project_path or os.getcwd()
        logger.info(f"Running verification checks in local workspace '{target_path}'")
        try:
            runs = run_local_verification(
                workspace_root=target_path,
                commands=payload.commands or ["pytest"],
            )
            return {
                "status": "success",
                "runs": runs,
            }
        except Exception as exc:
            logger.error(f"Failed to execute local verification: {exc}")
            raise HTTPException(status_code=400, detail=str(exc))

    # Asynchronous plan and SSOT generation
    background_tasks.add_task(process_plan, payload)
    return {"status": "accepted", "message": f"Delegated generation for {payload.plan_type}"}


if __name__ == "__main__":
    logger.info("Starting local ESSOT MCP Webhook Listener on port 8123...")
    uvicorn.run(app, host="0.0.0.0", port=8123)
