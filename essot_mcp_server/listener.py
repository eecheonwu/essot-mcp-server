import os
import sys
import json
import random
import asyncio
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any

# Ensure repository root is in sys.path for direct execution or standalone scripts
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pydantic import BaseModel

try:
    from essot_mcp_server.server import (
        generate_implementation_plan,
        generate_task_plan,
        generate_test_plan,
        get_knowledge_dir,
        get_project_root,
        _scaffold_agent_packages,
    )
    from essot_mcp_server.patcher import (
        apply_patch_to_local_workspace,
        run_local_verification,
        read_workspace_files,
    )
except (ImportError, ModuleNotFoundError):
    from server import (
        generate_implementation_plan,
        generate_task_plan,
        generate_test_plan,
        get_knowledge_dir,
        get_project_root,
        _scaffold_agent_packages,
    )
    from patcher import (
        apply_patch_to_local_workspace,
        run_local_verification,
        read_workspace_files,
    )

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("essot_worker")


class TriggerPayload(BaseModel):
    project_id: str
    plan_id: Optional[str] = None
    plan_type: str
    artifacts: List[Dict[str, Any]] = []
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
    """Processes incoming plan generation or local SSOT sync commands."""
    with plan_lock:
        if payload.api_key and not os.environ.get("ESSOT_API_KEY"):
            os.environ["ESSOT_API_KEY"] = payload.api_key
        if payload.api_url and not os.environ.get("ESSOT_API_URL"):
            os.environ["ESSOT_API_URL"] = payload.api_url

        knowledge_dir = get_knowledge_dir(payload.project_path)
        logger.info(f"Received task to process {payload.plan_type} in {knowledge_dir}")

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
            ssot_yaml_path.write_text(ssot_yaml_content, encoding="utf-8")

        # Map artifacts to appropriate directories
        for artifact in payload.artifacts:
            name = artifact.get("name", "artifact")
            if not name.endswith(".md") and not name.endswith(".yaml"):
                name += ".md"

            atype = str(artifact.get("type", "")).upper()
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

        if payload.graph_context:
            (knowledge_dir / "system" / "WEB_GRAPH_CONTEXT.md").write_text(payload.graph_context, encoding="utf-8")

        clean_pt = (payload.plan_type or "").strip().lower()
        if "implementation" in clean_pt:
            generate_implementation_plan(project_path=payload.project_path, provider=payload.provider)
        elif "task" in clean_pt:
            generate_task_plan(project_path=payload.project_path, provider=payload.provider)
        elif "test" in clean_pt:
            generate_test_plan(project_path=payload.project_path, provider=payload.provider)
        elif "ssot" in clean_pt:
            _scaffold_agent_packages(knowledge_dir)
            logger.info("Local SSOT successfully scaffolded. Multi-agent packages assembled.")
        else:
            logger.warning(f"Unknown plan type: {payload.plan_type}")

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


def execute_sync_task(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a task synchronously (invoked in a thread pool for outbound WebSocket worker).
    Handles:
      - Read Files
      - Apply Patch
      - Verify Patch
      - Write File
      - Local SSOT Sync & Plan Generations
    """
    plan_type = payload_dict.get("plan_type", "")
    target_path = payload_dict.get("project_path") or os.getcwd()

    if plan_type in ("Read Files", "Get Files", "File Content", "Inspect Files"):
        logger.info(f"Reading workspace files from '{target_path}': {payload_dict.get('touched_files')}")
        files_data = read_workspace_files(
            workspace_root=target_path,
            files=payload_dict.get("touched_files") or [],
        )
        return {
            "status": "success",
            "files": files_data,
        }

    elif plan_type in ("Apply Patch", "Patch", "Forge Patch"):
        logger.info(f"Applying patch to local workspace '{target_path}'")
        applied_files = apply_patch_to_local_workspace(
            workspace_root=target_path,
            diff=payload_dict.get("diff") or "",
            touched_files=payload_dict.get("touched_files") or None,
        )
        return {
            "status": "success",
            "message": f"Successfully applied patch to {len(applied_files)} files in {target_path}",
            "applied_files": applied_files,
        }

    elif plan_type in ("Verify Patch", "Run Verification", "Verification"):
        logger.info(f"Running verification checks in local workspace '{target_path}'")
        runs = run_local_verification(
            workspace_root=target_path,
            commands=payload_dict.get("commands") or ["pytest"],
        )
        return {
            "status": "success",
            "runs": runs,
        }

    elif plan_type in ("Write File", "Save File", "Write Plan", "Materialize File"):
        file_path = payload_dict.get("file_path") or "plan.md"
        content = payload_dict.get("content") or ""
        dest = get_project_root(target_path) / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        logger.info(f"Successfully wrote {len(content)} chars to {dest}")
        return {
            "status": "success",
            "message": f"Successfully wrote {file_path}",
            "file_path": str(dest)
        }

    else:
        # Plan or Local SSOT Sync
        payload_obj = TriggerPayload(**payload_dict)
        process_plan(payload_obj)
        return {
            "status": "success",
            "message": f"Successfully processed {plan_type} in workspace"
        }


async def run_outbound_websocket_worker():
    """
    Maintains a persistent, outbound WebSocket connection to the ESSOT Cloud backend.
    Enables permanent, zero-configuration enterprise communication.
    Zero open ports required on the local machine.
    """
    logged_missing_key = False
    retry_delay = 3.0

    while True:
        api_key = os.environ.get("ESSOT_API_KEY", "").strip()
        api_url = os.environ.get("ESSOT_API_URL", "https://essot.space").rstrip("/")

        # When user has not set ESSOT_API_KEY
        if not api_key:
            if not logged_missing_key:
                logger.warning(
                    "\n" + "=" * 78 + "\n"
                    " [NOTICE] ESSOT_API_KEY is not set.\n"
                    " • Outbound cloud tunnel to ESSOT Web App is paused.\n"
                    " • To enable permanent outbound tunnel mode:\n"
                    "     In Linux/macOS : export ESSOT_API_KEY=\"essot_your_api_key\"\n"
                    "     In Windows PS  : $env:ESSOT_API_KEY=\"essot_your_api_key\"\n"
                    + "=" * 78
                )
                logged_missing_key = True

            # Wait and check again without crashing
            await asyncio.sleep(5)
            continue

        logged_missing_key = False
        ws_base = api_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_endpoint = f"{ws_base}/api/v1/ws/worker?token={api_key}"

        logger.info(f"Connecting outbound WebSocket worker to {ws_base}...")

        try:
            import websockets
            async with websockets.connect(
                ws_endpoint,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            ) as ws:
                logger.info("🟢 Outbound WebSocket tunnel established with ESSOT Cloud. Permanent tunnel active.")
                retry_delay = 3.0

                while True:
                    msg_text = await ws.recv()
                    try:
                        data = json.loads(msg_text)
                    except Exception:
                        continue

                    if not isinstance(data, dict):
                        continue

                    msg_type = data.get("type")
                    if msg_type == "connected":
                        logger.info("🟢 Authenticated with ESSOT Cloud: %s", data.get("message"))
                        try:
                            await ws.send(json.dumps({
                                "type": "worker_info",
                                "client_name": "ESSOT Local MCP Server",
                                "version": "0.2.1"
                            }))
                        except Exception:
                            pass
                        continue
                    elif msg_type == "error":
                        logger.warning("🔴 Cloud authentication error: %s (Check your ESSOT_API_KEY)", data.get("message"))
                        await asyncio.sleep(10)
                        break
                    elif msg_type == "ping":
                        pong_payload = {
                            "type": "pong",
                            "request_id": data.get("request_id"),
                            "timestamp": data.get("timestamp")
                        }
                        await ws.send(json.dumps(pong_payload))
                        continue
                    elif msg_type == "pong":
                        continue

                    request_id = data.get("request_id")
                    if not request_id:
                        continue

                    plan_type = data.get("plan_type", "Unknown")
                    logger.info("📥 Received task dispatch from ESSOT Cloud: %s [request_id=%s]", plan_type, request_id)

                    try:
                        # Run execution in thread pool so it never blocks the WebSocket event loop
                        result = await asyncio.to_thread(execute_sync_task, data)
                        result["request_id"] = request_id
                        await ws.send(json.dumps(result))
                        logger.info("📤 Successfully completed and reported task [request_id=%s]", request_id)
                    except Exception as task_exc:
                        logger.error("❌ Error executing task %s: %s", request_id, task_exc)
                        await ws.send(json.dumps({
                            "request_id": request_id,
                            "status": "error",
                            "error": str(task_exc)
                        }))

        except asyncio.CancelledError:
            logger.info("WebSocket worker task cancelled.")
            break
        except Exception as exc:
            jitter = random.uniform(0.5, 1.5)
            sleep_time = retry_delay + jitter
            logger.warning("WebSocket worker connection blip (%s). Reconnecting in %.1fs...", exc, sleep_time)
            await asyncio.sleep(sleep_time)
            retry_delay = min(retry_delay * 1.5, 30.0)
