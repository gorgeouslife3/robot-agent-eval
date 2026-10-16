"""Fetch isolated source checkouts and record immutable revisions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import time

from .catalog import AUXILIARY_REPOS, METHODS


def fetch_sources(root: Path, jobs: int = 4) -> dict:
    repos = {m["directory"]: m["repo"] for m in METHODS if m["repo"]}
    repos.update(AUXILIARY_REPOS)
    destination = root / "sources"
    destination.mkdir(parents=True, exist_ok=True)
    records = {}

    def fetch(name, repo):
        checkout = destination / name
        started = time.monotonic()
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
        if not checkout.exists():
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", "--filter=blob:none", "https://github.com/" + repo + ".git", str(checkout)],
                capture_output=True, text=True, timeout=180, env=env,
            )
            if proc.returncode:
                return name, {"repo": repo, "status": "fetch_failed", "returncode": proc.returncode,
                              "error": proc.stderr[-1200:], "elapsed_s": time.monotonic() - started}
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=checkout, capture_output=True, text=True, check=True).stdout
        tracked = subprocess.run(["git", "ls-files"], cwd=checkout, capture_output=True, text=True, check=True).stdout.splitlines()
        return name, {"repo": repo, "status": "fetched", "revision": revision, "dirty": bool(status),
                      "path": str(checkout), "tracked_file_count": len(tracked),
                      "python_file_count": sum(p.endswith(".py") for p in tracked),
                      "elapsed_s": time.monotonic() - started}

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(fetch, name, repo): (name, repo) for name, repo in repos.items()}
        for future in as_completed(futures):
            name, repo = futures[future]
            try:
                name, record = future.result()
            except Exception as exc:
                record = {"repo": repo, "status": "fetch_failed", "error": type(exc).__name__ + ": " + str(exc)}
            records[name] = record
            print(name + ": " + record["status"], flush=True)
            # Preserve progress if the process is interrupted.
            (root / "source-lock.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    return records
