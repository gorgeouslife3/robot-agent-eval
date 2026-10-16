"""Owned output helpers and disjoint monotonic time accounting."""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parents[3]
OWNED = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def owned(path):
    path = Path(path).resolve()
    if not path.is_relative_to(OWNED):
        raise ValueError('Output outside isolated experiment: ' + str(path))
    return path


def write(path, data):
    path = owned(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def append(path, data):
    path = owned(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Ledger:
    def __init__(self, path):
        self.path = owned(path)
        self.sums = {}

    @contextmanager
    def measure(self, category, **metadata):
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            self.sums[category] = self.sums.get(category, 0.) + end - start
            append(self.path, dict(category=category, start_monotonic=start,
                                   end_monotonic=end, elapsed_s=end-start, **metadata))


def implementation_identity():
    return {p.name: sha(p) for p in sorted((OWNED/'implementation').glob('*.py'))}
