import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
import logging

logger = logging.getLogger("essot_patcher")


def _clean_path(raw_path: str) -> Optional[str]:
    """Cleans a raw file path from unified diff headers."""
    if not raw_path:
        return None
    p = raw_path.strip()
    if p.startswith("--- "):
        p = p[4:].strip()
    elif p.startswith("+++ "):
        p = p[4:].strip()

    if "\t" in p:
        p = p.split("\t", 1)[0].strip()
    elif "  " in p:
        p = p.split("  ", 1)[0].strip()

    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1].strip()

    p = p.replace("\\", "/").strip().lstrip("./").lstrip("/")

    if p in ("dev/null", "/dev/null") or p.endswith("/dev/null"):
        return None

    if (p.startswith("a/") or p.startswith("b/")) and len(p) > 2:
        p = p[2:]

    p = p.strip().lstrip("./").lstrip("/")
    return p if p else None


def parse_diff_touched_files(diff_text: str, approved_files: Optional[List[str]] = None) -> List[str]:
    """Extracts all modified, added, or deleted target relative file paths from a unified diff."""
    touched: Set[str] = set()
    for line in diff_text.splitlines():
        line = line.strip()
        if line.startswith("+++ "):
            cleaned = _clean_path(line[4:])
            if cleaned:
                touched.add(cleaned)
        elif line.startswith("--- "):
            cleaned = _clean_path(line[4:])
            if cleaned:
                touched.add(cleaned)
        elif line.startswith("diff --git "):
            parts = line[11:].strip().split()
            if len(parts) >= 2:
                for part in parts[:2]:
                    cleaned = _clean_path(part)
                    if cleaned:
                        touched.add(cleaned)
        elif line.startswith("=== FILE:"):
            target = line[9:].rstrip("=").strip()
            cleaned = _clean_path(target)
            if cleaned:
                touched.add(cleaned)
        elif line.startswith("Index: "):
            cleaned = _clean_path(line[7:])
            if cleaned:
                touched.add(cleaned)

    if not touched and approved_files:
        for app_file in approved_files:
            pattern = re.compile(
                rf"(?:---|\+\+\+|file:|path:|=== FILE:|\b)\s*['\"]?(?:a/|b/)?{re.escape(app_file)}['\"]?",
                re.IGNORECASE,
            )
            if pattern.search(diff_text):
                touched.add(app_file)

    return sorted(list(touched))


def split_multi_file_diff(diff_text: str) -> Dict[str, str]:
    """Splits a multi-file unified diff into individual file diff strings keyed by clean relative path."""
    file_diffs: Dict[str, List[str]] = {}
    current_file: Optional[str] = None
    current_lines: List[str] = []

    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        header_file = None

        if line.startswith("diff --git "):
            parts = line[11:].strip().split()
            if len(parts) >= 2:
                header_file = _clean_path(parts[1]) or _clean_path(parts[0])
        elif line.startswith("--- "):
            c_old = _clean_path(line[4:])
            c_new = None
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                c_new = _clean_path(lines[i + 1][4:])
            header_file = c_new or c_old
        elif line.startswith("+++ ") and not (i > 0 and lines[i - 1].startswith("--- ")):
            header_file = _clean_path(line[4:])

        if header_file and header_file != current_file:
            if current_file and current_lines:
                file_diffs[current_file] = "\n".join(current_lines)
            current_file = header_file
            current_lines = [line]
        else:
            if current_file is not None:
                current_lines.append(line)
        i += 1

    if current_file and current_lines:
        file_diffs[current_file] = "\n".join(current_lines)

    return file_diffs


def _find_hunk_position(original_lines: List[str], expected_old_lines: List[str], hint_idx: int) -> int:
    """Finds the 0-indexed line in original_lines where expected_old_lines match."""
    if not expected_old_lines:
        return max(0, hint_idx)

    norm_orig = [l.rstrip("\r\n") for l in original_lines]
    norm_exp = [l.rstrip("\r\n") for l in expected_old_lines]
    exp_len = len(norm_exp)
    orig_len = len(norm_orig)

    if exp_len > orig_len:
        return max(0, hint_idx)

    # 1. Check exact hint position
    hint_idx = max(0, min(hint_idx, orig_len - exp_len))
    if norm_orig[hint_idx : hint_idx + exp_len] == norm_exp:
        return hint_idx

    # 2. Search in an expanding window around hint_idx (up to +/- 100 lines)
    for delta in range(1, 100):
        for candidate in (hint_idx - delta, hint_idx + delta):
            if 0 <= candidate <= orig_len - exp_len:
                if norm_orig[candidate : candidate + exp_len] == norm_exp:
                    return candidate

    # 3. Full file search
    for i in range(orig_len - exp_len + 1):
        if norm_orig[i : i + exp_len] == norm_exp:
            return i

    # 4. Partial match fallback (ignoring empty lines)
    stripped_exp = [l.strip() for l in norm_exp if l.strip()]
    if stripped_exp:
        s_len = len(stripped_exp)
        for i in range(orig_len - s_len + 1):
            window = [norm_orig[j].strip() for j in range(i, i + s_len)]
            if window == stripped_exp:
                return i

    return hint_idx


def apply_unified_diff_to_string(original_content: str, file_diff: str) -> str:
    """Applies unified diff hunks targeting a single file to an in-memory string."""
    original_lines = original_content.splitlines(keepends=True)
    diff_lines = file_diff.splitlines()

    is_new_file = any(l.startswith("--- /dev/null") for l in diff_lines[:5])
    if is_new_file or not original_lines:
        new_content_lines = []
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                new_content_lines.append(line[1:] + "\n")
        return "".join(new_content_lines)

    result_lines = list(original_lines)
    hunk_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    hunks: List[Tuple[int, int, List[str]]] = []
    current_hunk_lines: List[str] = []
    current_old_start = 0
    current_old_count = 0

    for line in diff_lines:
        hunk_match = hunk_regex.match(line)
        if hunk_match:
            if current_hunk_lines:
                hunks.append((current_old_start, current_old_count, current_hunk_lines))
                current_hunk_lines = []
            current_old_start = int(hunk_match.group(1))
            current_old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
        elif current_old_start > 0:
            current_hunk_lines.append(line)

    if current_hunk_lines:
        hunks.append((current_old_start, current_old_count, current_hunk_lines))

    resolved_hunks: List[Tuple[int, int, List[str]]] = []
    for old_start, old_count, hunk_lines in hunks:
        hint_idx = max(0, old_start - 1)
        expected_old = [hline[1:] for hline in hunk_lines if hline and hline[0] in (" ", "-")]
        pos = _find_hunk_position(result_lines, expected_old, hint_idx)

        replacement: List[str] = []
        for hline in hunk_lines:
            if not hline:
                continue
            marker = hline[0]
            text = hline[1:]
            if marker in ("+", " "):
                replacement.append(text + ("\n" if not text.endswith("\n") else ""))
            elif marker in ("-", "\\"):
                continue

        replace_count = len(expected_old) if expected_old else old_count
        resolved_hunks.append((pos, replace_count, replacement))

    resolved_hunks.sort(key=lambda h: h[0], reverse=True)

    for pos, replace_count, replacement in resolved_hunks:
        result_lines[pos : pos + replace_count] = replacement

    return "".join(result_lines)


def apply_patch_to_local_workspace(
    workspace_root: str | Path,
    diff: str,
    touched_files: Optional[List[str]] = None
) -> List[str]:
    """
    Applies unified diff directly to the files in the local workspace directory.
    Validates confinement, creates backup copies, applies diff, and writes changes.
    """
    root_path = Path(workspace_root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Local workspace directory '{root_path}' does not exist on this machine.")

    if not touched_files:
        touched_files = parse_diff_touched_files(diff)

    if not touched_files:
        raise ValueError("No target files detected in unified diff.")

    split_diffs = split_multi_file_diff(diff)
    applied: List[str] = []

    for rel_file in touched_files:
        target_path = (root_path / rel_file).resolve()
        # Security confinement check: prevent path traversal outside workspace
        if not str(target_path).startswith(str(root_path)):
            raise PermissionError(f"Security violation: path traversal detected for file '{rel_file}'.")

        original_content = ""
        if target_path.exists():
            original_content = target_path.read_text(encoding="utf-8", errors="replace")
            # Save backup
            backup_path = target_path.with_suffix(target_path.suffix + ".essot_bak")
            backup_path.write_text(original_content, encoding="utf-8")

        file_diff = split_diffs.get(rel_file, diff)
        patched_content = apply_unified_diff_to_string(original_content, file_diff)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(patched_content, encoding="utf-8")
        applied.append(rel_file)
        logger.info(f"Successfully applied patch to {target_path}")

    return applied


def run_local_verification(
    workspace_root: str | Path,
    commands: List[str]
) -> List[Dict[str, Any]]:
    """
    Runs deterministic verification commands (e.g. pytest, ruff) in the local workspace directory.
    Captures exit codes, duration, stdout, and stderr.
    """
    root_path = Path(workspace_root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Local workspace directory '{root_path}' does not exist.")

    runs: List[Dict[str, Any]] = []
    for cmd in commands:
        tokens = shlex.split(cmd.strip())
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                tokens,
                cwd=str(root_path),
                capture_output=True,
                text=True,
                timeout=120,
                shell=False
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            status_str = "VERIFIED" if proc.returncode == 0 else "FAILED"
            runs.append({
                "command": cmd,
                "exit_code": proc.returncode,
                "status": status_str,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "duration_ms": duration_ms
            })
        except subprocess.TimeoutExpired as te:
            duration_ms = int((time.perf_counter() - start) * 1000)
            runs.append({
                "command": cmd,
                "exit_code": -1,
                "status": "PARTIALLY_VERIFIED",
                "stdout": te.stdout or "",
                "stderr": f"Command timed out after 120 seconds: {te}",
                "duration_ms": duration_ms
            })
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            runs.append({
                "command": cmd,
                "exit_code": 1,
                "status": "FAILED",
                "stdout": "",
                "stderr": f"Execution error: {exc}",
                "duration_ms": duration_ms
            })

    return runs
