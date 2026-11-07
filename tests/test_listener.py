import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from essot_mcp_server.listener import app, execute_sync_task, run_outbound_websocket_worker
import asyncio

client = TestClient(app)


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


def test_trigger_http_endpoint(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("data", encoding="utf-8")

    resp = client.post("/trigger", json={
        "project_id": "test-proj-123",
        "plan_type": "Read Files",
        "project_path": str(tmp_path),
        "touched_files": ["sample.txt"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "sample.txt" in data["files"]


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
