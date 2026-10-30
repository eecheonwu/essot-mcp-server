import os
import pytest
from pathlib import Path
from essot_mcp_server.patcher import (
    resolve_workspace_dir,
    remap_verification_command,
    run_local_verification,
)


def test_resolve_workspace_dir(tmp_path: Path):
    # Setup mock structure:
    # tmp_path/src/frontend
    # tmp_path/src/backend
    (tmp_path / "src" / "frontend").mkdir(parents=True)
    (tmp_path / "src" / "backend").mkdir(parents=True)

    assert resolve_workspace_dir(tmp_path, "frontend") == (tmp_path / "src" / "frontend")
    assert resolve_workspace_dir(tmp_path, "backend") == (tmp_path / "src" / "backend")
    assert resolve_workspace_dir(tmp_path, "src/frontend") == (tmp_path / "src" / "frontend")
    assert resolve_workspace_dir(tmp_path, "nonexistent") is None


def test_remap_verification_command_chained(tmp_path: Path):
    frontend_dir = tmp_path / "src" / "frontend"
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package.json").write_text('{"scripts": {"build": "vite build"}}', encoding="utf-8")

    cmd = "cd frontend && npm test"
    remapped, target_cwd = remap_verification_command(tmp_path, cmd)

    if os.name == "nt":
        assert 'cd /d "src\\frontend" && npm run build' in remapped
    else:
        assert 'cd "src/frontend" && npm run build' in remapped
    assert target_cwd == frontend_dir


def test_remap_verification_command_standalone_cd(tmp_path: Path):
    frontend_dir = tmp_path / "src" / "frontend"
    frontend_dir.mkdir(parents=True)

    cmd = "cd frontend"
    remapped, target_cwd = remap_verification_command(tmp_path, cmd)

    if os.name == "nt":
        assert 'cd /d "src\\frontend"' == remapped
    else:
        assert 'cd "src/frontend"' == remapped
    assert target_cwd == frontend_dir


def test_run_local_verification_success(tmp_path: Path):
    (tmp_path / "src" / "frontend").mkdir(parents=True)
    (tmp_path / "src" / "frontend" / "package.json").write_text('{"scripts": {"build": "echo BUILD_OK"}}', encoding="utf-8")

    runs = run_local_verification(
        workspace_root=tmp_path,
        commands=["cd frontend && npm run build"]
    )
    assert len(runs) == 1
    assert runs[0]["status"] == "VERIFIED"
    assert runs[0]["exit_code"] == 0
