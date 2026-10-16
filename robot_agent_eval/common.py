"""Small evidence helpers; credentials are never serialized to run outputs."""
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIM_PYTHON = os.environ.get('ROBOT_EVAL_SIM_PYTHON', sys.executable)
ROBODOJO = Path(os.environ.get('ROBODOJO_ROOT', ROOT.parent / 'RoboDojo')).expanduser().resolve()
ASTRA = Path(os.environ.get('ROBOT_EVAL_ASTRA_ROOT', ROOT/'source-snapshots/astra_policy')).expanduser().resolve()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(config):
    if os.environ.get('OPENAI_API_KEY'):
        return os.environ['OPENAI_API_KEY']
    credential = Path(config['api_key_file']).expanduser()
    if not credential.is_absolute():
        credential = ROOT / credential
    value = credential.read_text().strip()
    if config.get('api_key_json_field'):
        value = json.loads(value)[config['api_key_json_field']]
    if not isinstance(value, str) or not value:
        raise ValueError('Configured credential is empty')
    return value


def verify_case(case):
    if sha(case['layout_path']) != case['layout_sha256']:
        raise ValueError('Frozen layout changed')
    inventory = read(ROOT/'manifests/inventory.json')
    for name, digest in inventory['environment']['files'].items():
        if sha(ROBODOJO/name) != digest:
            raise ValueError('Native source/config changed: '+name)


def source_path():
    import sys
    sys.path.insert(0, str(ASTRA))
