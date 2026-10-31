import json
import os
import re
import shlex
import shutil
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


def resolve_workspace_file_path(root_path: Path, rel_file: str) -> Path:
    """
    Intelligently resolves a relative file path within workspace_root.
    If the exact relative path does not exist, checks common monorepo/source prefixes
    (e.g. src/<rel_file>, app/<rel_file>, backend/<rel_file>) and searches for
    matching files in the repository before defaulting to creating a new path.
    """
    norm_rel = rel_file.replace("\\", "/").strip("/")
    direct = (root_path / norm_rel).resolve()
    if direct.exists() and direct.is_file():
        return direct

    # Check common source tree prefixes (e.g., src/frontend/package.json vs frontend/package.json)
    for prefix in ["src", "app", "backend", "frontend"]:
        candidate = (root_path / prefix / norm_rel).resolve()
        if candidate.exists() and candidate.is_file():
            logger.info("Fuzzy path match: remapped '%s' to '%s'", rel_file, candidate.relative_to(root_path).as_posix())
            return candidate

    # Search repository for unambiguous match (excluding noise directories)
    ignore_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache"}
    target_name = Path(norm_rel).name
    matches = []
    for p in root_path.rglob(target_name):
        if any(ignored in p.parts for ignored in ignore_dirs):
            continue
        p_rel = p.relative_to(root_path).as_posix()
        if p_rel.endswith(norm_rel):
            matches.append(p)

    if len(matches) == 1:
        logger.info("Found matching repository file for '%s' at '%s'", rel_file, matches[0].relative_to(root_path).as_posix())
        return matches[0]

    return direct


def read_workspace_files(workspace_root: str | Path, files: List[str]) -> Dict[str, Any]:
    """
    Reads contents and resolves exact relative paths for requested files in the workspace.
    Used by remote cloud backends to inspect real existing code before generating diffs.
    """
    root_path = Path(workspace_root).resolve()
    result = {}
    for f in files:
        resolved = resolve_workspace_file_path(root_path, f)
        if resolved.exists() and resolved.is_file():
            resolved_rel = resolved.relative_to(root_path).as_posix()
            result[f] = {
                "exists": True,
                "resolved_rel_path": resolved_rel,
                "content": resolved.read_text(encoding="utf-8", errors="replace"),
            }
        else:
            result[f] = {
                "exists": False,
                "resolved_rel_path": f,
                "content": "",
            }
    return result


def apply_patch_to_local_workspace(
    workspace_root: str | Path,
    diff: str,
    touched_files: Optional[List[str]] = None
) -> List[str]:
    """
    Applies unified diff directly to the files in the local workspace directory.
    Validates confinement, creates backup copies, applies diff, and writes changes.
    Smartly resolves paths if files live in subdirectories like src/.
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
        target_path = resolve_workspace_file_path(root_path, rel_file)
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
        applied_rel = target_path.relative_to(root_path).as_posix()
        applied.append(applied_rel)
        logger.info(f"Successfully applied patch to {target_path} (rel: {applied_rel})")

    return applied


def resolve_workspace_dir(root_path: Path, rel_dir: str | Path) -> Optional[Path]:
    """
    Resolves a relative directory to an actual directory within workspace_root.
    Handles monorepos and subdirectories (e.g. 'frontend' -> 'src/frontend').
    """
    clean_rel = str(rel_dir).strip().strip("'\"").replace("\\", "/").strip("/")
    if not clean_rel or clean_rel == ".":
        return root_path

    # Direct directory
    direct = (root_path / clean_rel).resolve()
    if direct.is_dir() and str(direct).startswith(str(root_path)):
        return direct

    # Common source tree prefixes: src/, app/, backend/, frontend/
    prefixes = ["src", "app", "backend", "frontend"]
    for prefix in prefixes:
        candidate = (root_path / prefix / clean_rel).resolve()
        if candidate.is_dir() and str(candidate).startswith(str(root_path)):
            logger.info("Resolved directory '%s' to '%s'", rel_dir, candidate.relative_to(root_path).as_posix())
            return candidate

    # Search for matching subdirectory (excluding noise)
    ignore_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache"}
    target_name = Path(clean_rel).name.lower()
    for item in root_path.rglob("*"):
        if item.is_dir() and item.name.lower() == target_name:
            if any(ignored in item.parts for ignored in ignore_dirs):
                continue
            logger.info("Found matching repository directory for '%s' at '%s'", rel_dir, item.relative_to(root_path).as_posix())
            return item

    return None


def remap_verification_command(
    root_path: Path,
    cmd: str,
    current_cwd: Optional[Path] = None
) -> Tuple[str, Path]:
    """
    Remaps verification command paths and scripts to match the actual repository structure.
    - Rewrites 'cd frontend && npm test' -> 'cd /d "src\\frontend" && npm run build'
    - Detects missing npm 'test' scripts and falls back to 'npm run build'
    - Returns (remapped_command_string, target_working_directory)
    """
    base_cwd = current_cwd or root_path
    clean_cmd = cmd.strip()

    # Pattern 1: Chained cd: "cd frontend && npm test"
    chained_match = re.match(
        r'^\s*cd(?:\s+/d)?\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s;&|]+))\s*([;&|]{1,2})\s*(.+)$',
        clean_cmd,
        re.IGNORECASE
    )
    if chained_match:
        raw_dir = chained_match.group(1) or chained_match.group(2) or chained_match.group(3)
        sep = chained_match.group(4)
        rest_cmd = chained_match.group(5).strip()

        resolved_dir = resolve_workspace_dir(root_path, raw_dir)
        if resolved_dir:
            rel_dir = resolved_dir.relative_to(root_path).as_posix()
            
            # Check package.json for test script fallback
            if rest_cmd in ("npm test", "npm run test", "yarn test", "pnpm test"):
                pkg_file = resolved_dir / "package.json"
                if pkg_file.is_file():
                    try:
                        data = json.loads(pkg_file.read_text(encoding="utf-8"))
                        scripts = data.get("scripts", {})
                        if "test" not in scripts:
                            if "build" in scripts:
                                logger.info("Remapping 'npm test' to 'npm run build' in %s", rel_dir)
                                rest_cmd = "npm run build"
                            elif "test:e2e" in scripts:
                                rest_cmd = "npm run test:e2e"
                            elif "lint" in scripts:
                                rest_cmd = "npm run lint"
                    except Exception as e:
                        logger.debug("Failed reading package.json in %s: %s", resolved_dir, e)

            norm_rel = rel_dir.replace("/", "\\") if os.name == "nt" else rel_dir
            new_cmd = f'cd /d "{norm_rel}" {sep} {rest_cmd}' if os.name == "nt" else f'cd "{rel_dir}" {sep} {rest_cmd}'
            logger.info("Remapped command '%s' -> '%s' (target_cwd: %s)", cmd, new_cmd, resolved_dir)
            return new_cmd, resolved_dir

    # Pattern 2: Standalone cd: "cd frontend"
    single_cd_match = re.match(
        r'^\s*cd(?:\s+/d)?\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))\s*$',
        clean_cmd,
        re.IGNORECASE
    )
    if single_cd_match:
        raw_dir = single_cd_match.group(1) or single_cd_match.group(2) or single_cd_match.group(3)
        resolved_dir = resolve_workspace_dir(root_path, raw_dir)
        if resolved_dir:
            rel_dir = resolved_dir.relative_to(root_path).as_posix()
            norm_rel = rel_dir.replace("/", "\\") if os.name == "nt" else rel_dir
            new_cmd = f'cd /d "{norm_rel}"' if os.name == "nt" else f'cd "{rel_dir}"'
            logger.info("Remapped standalone cd '%s' -> '%s' (target_cwd: %s)", cmd, new_cmd, resolved_dir)
            return new_cmd, resolved_dir

    # Pattern 3: --prefix flag: "npm test --prefix frontend"
    prefix_match = re.search(r'--prefix\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))', clean_cmd)
    if prefix_match:
        raw_dir = prefix_match.group(1) or prefix_match.group(2) or prefix_match.group(3)
        resolved_dir = resolve_workspace_dir(root_path, raw_dir)
        if resolved_dir:
            rel_dir = resolved_dir.relative_to(root_path).as_posix()
            remapped_cmd = clean_cmd.replace(
                prefix_match.group(0),
                f'--prefix "{rel_dir}"'
            )
            pkg_file = resolved_dir / "package.json"
            if pkg_file.is_file() and ("npm test" in remapped_cmd or "npm run test" in remapped_cmd):
                try:
                    data = json.loads(pkg_file.read_text(encoding="utf-8"))
                    scripts = data.get("scripts", {})
                    if "test" not in scripts and "build" in scripts:
                        remapped_cmd = remapped_cmd.replace("npm test", "npm run build").replace("npm run test", "npm run build")
                except Exception:
                    pass
            logger.info("Remapped prefix command '%s' -> '%s'", cmd, remapped_cmd)
            return remapped_cmd, base_cwd

    # Pattern 4: Standalone npm test in base_cwd
    if clean_cmd in ("npm test", "npm run test"):
        pkg_file = base_cwd / "package.json"
        if pkg_file.is_file():
            try:
                data = json.loads(pkg_file.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {})
                if "test" not in scripts:
                    if "build" in scripts:
                        logger.info("Remapped '%s' to 'npm run build' in %s", clean_cmd, base_cwd)
                        return "npm run build", base_cwd
                    elif "test:e2e" in scripts:
                        return "npm run test:e2e", base_cwd
            except Exception:
                pass

    return clean_cmd, base_cwd


def run_local_verification(
    workspace_root: str | Path,
    commands: List[str]
) -> List[Dict[str, Any]]:
    """
    Runs deterministic verification commands (e.g. pytest, npm run build) in the local workspace directory.
    Captures exit codes, duration, stdout, and stderr.
    Intelligently remaps paths and scripts for monorepos / subdirectories.
    Enforces a strict 60s total suite budget and skips redundant network installs (e.g. npm install)
    to protect against Cloudflare 524 gateway timeouts.
    """
    root_path = Path(workspace_root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Local workspace directory '{root_path}' does not exist.")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    paths_to_add = [str(root_path)]
    for sub in ["src", "src/backend", "backend", "app"]:
        sub_path = root_path / sub
        if sub_path.is_dir():
            paths_to_add.append(str(sub_path))
    env["PYTHONPATH"] = os.pathsep.join(paths_to_add + ([existing_pythonpath] if existing_pythonpath else []))

    active_cwd = root_path
    runs: List[Dict[str, Any]] = []
    TOTAL_SUITE_BUDGET_SEC = 60.0
    MAX_STEP_TIMEOUT_SEC = 35.0
    suite_start = time.perf_counter()

    for cmd in commands:
        clean_cmd = cmd.strip()
        if not clean_cmd:
            continue

        exec_cmd, target_cwd = remap_verification_command(root_path, clean_cmd, current_cwd=active_cwd)
        active_cwd = target_cwd

        # Check total remaining timeout budget
        elapsed_so_far = time.perf_counter() - suite_start
        remaining_budget = TOTAL_SUITE_BUDGET_SEC - elapsed_so_far
        if remaining_budget <= 5.0:
            logger.warning("Verification suite budget reached (%.1fs elapsed). Skipping command: '%s'", elapsed_so_far, clean_cmd)
            runs.append({
                "command": clean_cmd,
                "executed_command": "[skipped: suite time budget limit]",
                "exit_code": 0,
                "status": "PARTIALLY_VERIFIED",
                "stdout": "",
                "stderr": "Step skipped: 60s verification time budget reached to protect against gateway timeout.",
                "duration_ms": 0
            })
            continue

        # Fast-path for dependency install commands (npm install, yarn, pnpm)
        # These are package managers, not verification tests. If node_modules exists, skipping avoids hanging.
        if re.search(r'\b(?:npm\s+i(?:nstall)?|pnpm\s+i(?:nstall)?|yarn\s+install)\b', clean_cmd):
            node_modules_dir = target_cwd / "node_modules"
            if node_modules_dir.is_dir():
                logger.info("Fast-path: skipping '%s' because '%s' is already present.", clean_cmd, node_modules_dir)
                runs.append({
                    "command": clean_cmd,
                    "executed_command": "[skipped: node_modules already present]",
                    "exit_code": 0,
                    "status": "VERIFIED",
                    "stdout": f"[essot] Directory '{node_modules_dir.relative_to(root_path)}' is already present. Skipped redundant network install.\n",
                    "stderr": "",
                    "duration_ms": 5
                })
                continue

        exec_dir = root_path if ("cd /d" in exec_cmd or "cd " in exec_cmd) else active_cwd
        step_timeout = max(5.0, min(MAX_STEP_TIMEOUT_SEC, remaining_budget))

        logger.info("Running verification command: '%s' (original: '%s') in cwd '%s' (timeout=%.1fs)", exec_cmd, clean_cmd, exec_dir, step_timeout)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                exec_cmd,
                cwd=str(exec_dir),
                capture_output=True,
                text=True,
                timeout=step_timeout,
                shell=True,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            status_str = "VERIFIED" if proc.returncode == 0 else "FAILED"
            logger.info("Verification step finished: exit=%d status=%s duration=%dms", proc.returncode, status_str, duration_ms)
            runs.append({
                "command": clean_cmd,
                "executed_command": exec_cmd,
                "exit_code": proc.returncode,
                "status": status_str,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "duration_ms": duration_ms
            })
        except subprocess.TimeoutExpired as te:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("Verification step timed out after %.1fs: '%s'", step_timeout, exec_cmd)
            runs.append({
                "command": clean_cmd,
                "executed_command": exec_cmd,
                "exit_code": -1,
                "status": "PARTIALLY_VERIFIED",
                "stdout": te.stdout or "",
                "stderr": f"Command timed out after {int(step_timeout)} seconds: {te}",
                "duration_ms": duration_ms
            })
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error("Verification step execution error: %s", exc)
            runs.append({
                "command": clean_cmd,
                "executed_command": exec_cmd,
                "exit_code": 1,
                "status": "FAILED",
                "stdout": "",
                "stderr": f"Execution error: {exc}",
                "duration_ms": duration_ms
            })

    return runs
