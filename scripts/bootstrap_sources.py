"""Restore selected external source snapshots at the committed revisions."""
import argparse
import hashlib
import io
import json
import tarfile
from pathlib import PurePosixPath
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_agent_eval.snapshots import fetch_snapshots, request


def restore_official_skill():
    """Download the anonymous registry artifact only if its pinned identity matches."""
    lock = json.loads((ROOT/'runtime-source-lock.json').read_text())['phyagentos-robodojo-skill']
    destination = ROOT/'runtime-sources/phyagentos-robodojo-skill'
    receipt = destination/'.bundle-identity.json'
    if receipt.exists():
        identity = json.loads(receipt.read_text())
        if identity.get('sha256') != lock['sha256']:
            raise ValueError('Cached skill identity differs from runtime-source-lock.json')
        for name, digest in identity['files'].items():
            if hashlib.sha256((destination/name).read_bytes()).hexdigest() != digest:
                raise ValueError('Cached skill changed: ' + name)
        print('phyagentos-robodojo-skill: verified_cached')
        return
    if destination.exists():
        raise ValueError('Inspect existing skill directory before restoring: ' + str(destination))
    with request(lock['registry_url']) as response:
        artifact = json.load(response)
    if artifact.get('sha256') != lock['sha256'] or artifact.get('size') != lock['size']:
        raise ValueError('Registry skill differs from the locked 0.2.1 artifact')
    with request(artifact['download_url']) as response:
        data = response.read(lock['size'] + 1)
    if len(data) != lock['size'] or hashlib.sha256(data).hexdigest() != lock['sha256']:
        raise ValueError('Official skill size/checksum mismatch')
    archive = tarfile.open(fileobj=io.BytesIO(data), mode='r:gz')
    files = {}
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError('Unsafe official skill archive member')
    if sum(member.size for member in members) > 16 * 1024 * 1024:
        raise ValueError('Official skill extracted size exceeds limit')
    for member in members:
        if not member.isfile():
            continue
        content = archive.extractfile(member).read()
        target = destination/member.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if member.mode & 0o111 else 0o644)
        files[member.name] = hashlib.sha256(content).hexdigest()
    receipt.write_text(json.dumps(dict(sha256=lock['sha256'], files=files), indent=2)+'\n')
    print('phyagentos-robodojo-skill: verified_download')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--names', nargs='+', default=['astra_policy', 'gap', 'phyagentos'])
    parser.add_argument('--jobs', type=int, default=3)
    args = parser.parse_args()
    records = fetch_snapshots(ROOT, args.jobs, args.names)
    failed = [name for name in args.names if records[name]['status'] != 'snapshot_fetched']
    if failed:
        for name in failed:
            print(name + ': ' + records[name].get('error', records[name]['status']), file=sys.stderr)
        raise SystemExit(1)
    restore_official_skill()


if __name__ == '__main__':
    main()
