"""Pinned GitHub code snapshots, avoiding slow Git smart-HTTP transfers."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import time
import urllib.request
import zipfile

from .catalog import AUXILIARY_REPOS, METHODS


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "RoboDojo-local-research"}), timeout=60)


def fetch_snapshots(root: Path, jobs=4, names=None):
    repos = {m["directory"]: m["repo"] for m in METHODS if m["repo"]}
    repos.update(AUXILIARY_REPOS)
    if names is not None:
        unknown = set(names) - repos.keys()
        if unknown:
            raise ValueError("Unknown sources: " + ", ".join(sorted(unknown)))
        repos = {name: repos[name] for name in names}
    base = root / "source-snapshots"
    base.mkdir(parents=True, exist_ok=True)
    lockfile = root / "source-lock.json"
    records = json.loads(lockfile.read_text()) if lockfile.exists() else {}

    def fetch(name, repo):
        prior = records.get(name, {})
        destination = base / name
        metadata = destination / ".snapshot.json"
        if metadata.exists():
            identity = json.loads(metadata.read_text())
            if identity.get("revision") != prior.get("revision"):
                raise RuntimeError("Existing snapshot revision differs from source-lock.json: " + name)
            return name, dict(prior, status="snapshot_fetched", path=str(destination.relative_to(root)))
        started = time.monotonic()
        revision = prior.get("revision")
        if not revision:
            with request("https://api.github.com/repos/" + repo + "/commits?per_page=1") as response:
                commits = json.load(response)
            revision = commits[0]["sha"]
        record = dict(repo=repo, revision=revision, fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        if prior.get("commit_date"):
            record["commit_date"] = prior["commit_date"]
        if name == "physevo_site":
            with request("https://api.github.com/repos/" + repo + "/git/trees/" + revision + "?recursive=1") as response:
                tree = json.load(response)
            record.update(status="website_only", tracked_file_count=len(tree.get("tree", [])),
                          python_file_count=sum(x["path"].endswith(".py") for x in tree.get("tree", [])),
                          path=None, tree=tree.get("tree", []))
            return name, record
        destination = base / name
        if destination.exists():
            # Never merge a different revision into an old checkout.
            raise RuntimeError("Existing unrecorded snapshot must be inspected: " + str(destination))
        with request("https://codeload.github.com/" + repo + "/zip/" + revision) as response:
            limit = 96 * 1024 * 1024
            archive_bytes = response.read(limit + 1)
        if len(archive_bytes) > limit:
            raise RuntimeError("Archive exceeds the 96 MiB source-only download limit")
        expected = prior.get("archive_sha256")
        if expected and hashlib.sha256(archive_bytes).hexdigest() != expected:
            raise ValueError("Pinned archive checksum mismatch: " + name)
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        hashes = {}
        skipped = 0
        for member in archive.infolist():
            relative = PurePosixPath(*PurePosixPath(member.filename).parts[1:])
            if not relative.parts or member.is_dir():
                continue
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive member")
            if relative.suffix.lower() in {".mp4", ".webm", ".mov", ".gif", ".pth", ".pt", ".ckpt", ".safetensors"}:
                skipped += 1
                continue
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(member)
            target.write_bytes(data)
            if (member.external_attr >> 16) & 0o111:
                target.chmod(0o755)
            hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        (destination / ".snapshot.json").write_text(json.dumps(dict(repo=repo, revision=revision, sha256=hashes), indent=2) + "\n")
        record.update(status="snapshot_fetched", path=str(destination.relative_to(root)), source_file_count=len(hashes),
                      python_file_count=sum(x.endswith(".py") for x in hashes), omitted_media_or_weights=skipped,
                      archive_sha256=hashlib.sha256(archive_bytes).hexdigest(), elapsed_s=time.monotonic() - started)
        return name, record

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(fetch, name, repo): (name, repo) for name, repo in repos.items()}
        for future in as_completed(futures):
            name, repo = futures[future]
            try:
                name, record = future.result()
            except Exception as exc:
                record = dict(repo=repo, status="fetch_failed", error=type(exc).__name__ + ": " + str(exc))
            records[name] = record
            lockfile.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
            print(name + ": " + record["status"], flush=True)
    return records
