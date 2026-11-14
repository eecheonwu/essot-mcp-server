import os
import pytest
from pathlib import Path
import asyncio

from essot_mcp_server.listener import execute_sync_task, run_outbound_websocket_worker
from essot_mcp_server.server import initialize_local_ssot, generate_implementation_plan


def test_missing_api_key_does_not_crash(monkeypatch):
    """Ensure missing ESSOT_API_KEY logs cleanly and does not crash the background worker loop."""
    monkeypatch.delenv("ESSOT_API_KEY", raising=False)

    async def run_short_check():
        task = asyncio.create_task(run_outbound_websocket_worker())
        await asyncio.sleep(0.1)
        assert not task.done(), "Worker loop should keep running peacefully even if ESSOT_API_KEY is not set"
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_short_check())


def test_execute_sync_task_read_files(tmp_path: Path):
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('test message')", encoding="utf-8")

    payload = {
        "plan_type": "Read Files",
        "project_path": str(tmp_path),
        "touched_files": ["hello.py"]
    }
    result = execute_sync_task(payload)
    assert result["status"] == "success"
    assert "hello.py" in result["files"]
    assert result["files"]["hello.py"]["content"] == "print('test message')"


def test_execute_sync_task_apply_patch(tmp_path: Path):
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    diff_content = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )

    payload = {
        "plan_type": "Apply Patch",
        "project_path": str(tmp_path),
        "diff": diff_content,
        "touched_files": ["calc.py"]
    }
    result = execute_sync_task(payload)
    assert result["status"] == "success"
    assert "calc.py" in result["applied_files"]
    assert "return a + b" in target.read_text(encoding="utf-8")


def test_execute_sync_task_write_file(tmp_path: Path):
    payload = {
        "plan_type": "Write File",
        "project_path": str(tmp_path),
        "file_path": "implementation-plan.md",
        "content": "# Test Implementation Plan Content\n\n- Task 1"
    }
    result = execute_sync_task(payload)
    assert result["status"] == "success"
    written_file = tmp_path / "implementation-plan.md"
    assert written_file.exists()
    assert "# Test Implementation Plan Content" in written_file.read_text(encoding="utf-8")


def test_execute_sync_task_local_ssot_sync(tmp_path: Path):
    payload = {
        "project_id": "proj-abc-123",
        "plan_type": "Local SSOT Sync",
        "project_path": str(tmp_path),
        "artifacts": [
            {"name": "user-auth.md", "type": "SRD", "content": "# User Auth Requirements"},
            {"name": "ADR-001.md", "type": "ADR", "content": "# ADR 001 Architecture"}
        ]
    }
    result = execute_sync_task(payload)
    assert result["status"] == "success"

    ssot_dir = tmp_path / "ssot"
    assert (ssot_dir / "requirements" / "user-auth.md").exists()
    assert (ssot_dir / "architecture" / "ADR-001.md").exists()
    assert (ssot_dir / "ssot.yaml").exists()
    assert (ssot_dir / "agents" / "frontend_agent.md").exists()
    assert (ssot_dir / "agents" / "backend_agent.md").exists()
    assert (ssot_dir / "agents" / "qa_agent.md").exists()


def test_initialize_local_ssot_tool(tmp_path: Path, monkeypatch):
    """Test initialize_local_ssot tool scaffolds directory and manifests cleanly."""
    monkeypatch.delenv("ESSOT_API_KEY", raising=False)
    res = initialize_local_ssot("00000000-0000-0000-0000-000000000001", project_path=str(tmp_path))
    assert "Successfully scaffolded local SSOT" in res

    ssot_dir = tmp_path / "ssot"
    assert (ssot_dir / "requirements" / "SRD.md").exists()
    assert (ssot_dir / "ssot.yaml").exists()
    assert (ssot_dir / "agents" / "backend_agent.md").exists()


def test_plan_generation_requires_api_key(tmp_path: Path, monkeypatch):
    """Test that plan generation safely checks for API key and returns informative error without crashing."""
    monkeypatch.delenv("ESSOT_API_KEY", raising=False)
    # create ssot.yaml so project_id is found
    ssot_dir = tmp_path / "ssot"
    ssot_dir.mkdir(parents=True)
    (ssot_dir / "ssot.yaml").write_text("project_id: test-proj-id\n", encoding="utf-8")

    res = generate_implementation_plan(project_path=str(tmp_path))
    assert "ESSOT_API_KEY environment variable is not set" in res
