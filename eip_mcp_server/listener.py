import os
import logging
import sys
from fastapi import FastAPI, BackgroundTasks
import uvicorn
from pydantic import BaseModel

# Import our MCP server functions directly
from eip_mcp_server.server import (
    generate_implementation_plan,
    generate_task_plan,
    generate_test_plan,
    get_knowledge_dir
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("trigger_listener")

app = FastAPI()

from typing import List, Dict

class TriggerPayload(BaseModel):
    project_id: str
    plan_id: str = None
    plan_type: str
    artifacts: List[Dict] = []
    graph_context: str = ""
    project_path: str = None
    provider: str = "openrouter"

import threading
plan_lock = threading.Lock()

def process_plan(payload: TriggerPayload):
    with plan_lock:
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
    description: "Local Engineering SSOT synchronized from EIP Web App"
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
            elif atype == "ADR" or atype == "UML" or atype == "C4":
                target_path = knowledge_dir / "architecture" / name
            elif atype == "TEST_SPEC" or atype == "Test Spec":
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
            from eip_mcp_server.server import _get_context
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
            # Default to implementation plan
            generate_implementation_plan(project_path=payload.project_path, provider=payload.provider)
            
        if payload.plan_id:
            try:
                import httpx
                eip_api_url = os.environ.get("EIP_API_URL", "http://localhost:8000").rstrip("/")
                headers = {}
                eip_api_key = os.environ.get("EIP_API_KEY")
                if eip_api_key:
                    headers["Authorization"] = f"Bearer {eip_api_key}"
                
                httpx.post(f"{eip_api_url}/api/v1/plans/{payload.plan_id}/complete", headers=headers, timeout=5.0)
                logger.info(f"Successfully notified backend of plan completion for {payload.plan_id}")
            except Exception as e:
                logger.error(f"Failed to notify backend of plan completion: {e}")
    
@app.post("/trigger")
async def trigger_webhook(payload: TriggerPayload, background_tasks: BackgroundTasks):
    """Webhook listener that kicks off the background MCP generation."""
    logger.info(f"Webhook hit for project {payload.project_id}")
    background_tasks.add_task(process_plan, payload)
    return {"status": "accepted", "message": f"Delegated generation for {payload.plan_type}"}

if __name__ == "__main__":
    logger.info("Starting local EIP MCP Webhook Listener on port 8123...")
    uvicorn.run(app, host="0.0.0.0", port=8123)
