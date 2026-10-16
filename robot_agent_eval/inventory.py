"""Task/layout identity and source locking without launching the simulator."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

PILOT_TASKS = ["general_pickup", "align_blocks", "stack_bowls", "stack_bowls_random",
               "swap_blocks", "insert_tubes", "put_bottles_into_dustbin"]


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(path: Path):
    def git(*args):
        p = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    return dict(revision=git("rev-parse", "HEAD"), status=git("status", "--porcelain"),
                diff_sha256=hashlib.sha256((git("diff", "--no-ext-diff") or "").encode()).hexdigest())


def build_inventory(robodojo: Path, root: Path, python: str, eval_seed=0):
    proc = subprocess.run([python, str(robodojo / "scripts/internal/task_inventory.py"), "--format", "json", "--check"],
                          cwd=robodojo, capture_output=True, text=True, check=True)
    native = json.loads(proc.stdout)
    # Parse YAML in the already configured simulator interpreter, not base conda.
    proc = subprocess.run([python, "-c", "import json,yaml,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
                           str(robodojo / "task/RoboDojo/config/_task.yml")], capture_output=True, text=True, check=True)
    task_cfg = json.loads(proc.stdout)
    records = []
    test = []
    development = []
    layout_root = robodojo / "Assets/Eval_Layout/RoboDojo/arx_x5" / str(eval_seed)
    for task in native["tasks"]:
        name = task["name"]
        pattern = re.compile(re.escape(name) + r"_\d+\.json")
        layouts = sorted((p for p in layout_root.iterdir() if pattern.fullmatch(p.name)),
                         key=lambda p: int(p.stem.rsplit("_", 1)[-1]))
        native_count = int(task_cfg.get("tasks", {}).get(name, {}).get("eval_nums", task_cfg["common"]["eval_nums"]))
        cfg_path = robodojo / task["config"]
        runtime_path = robodojo / task["module"]
        step_match = re.search(r"self\.step_lim\s*=\s*(\d+)", runtime_path.read_text())
        record = dict(task, native_eval_count=native_count, layout_count=len(layouts),
                      config_sha256=sha256(cfg_path), module_sha256=sha256(runtime_path),
                      declared_step_limit=int(step_match.group(1)) if step_match else None)
        records.append(record)
        for ordinal, path in enumerate(layouts):
            case = dict(case_id=f"{name}:seed{eval_seed}:layout{ordinal}", task=name,
                        dimension=task["dimension"], variant=task["variant"], eval_seed=eval_seed,
                        layout_id=ordinal, layout_filename=path.name, layout_path=str(path),
                        layout_sha256=sha256(path), config_sha256=record["config_sha256"],
                        native_step_limit=record["declared_step_limit"], env_cfg="arx_x5")
            (test if ordinal < native_count else development).append(case)
    # Extra files are not automatically independent: some native layouts repeat.
    test_hashes = {c['layout_sha256'] for c in test}
    overlap = [c for c in development if c['layout_sha256'] in test_hashes]
    development = [c for c in development if c['layout_sha256'] not in test_hashes]
    # No object/layout contents are exported to the agent. These manifests are evaluator-owned.
    version_paths = ["env_cfg/arx_x5.yml", "env_cfg/sim/sim_config.yml", "env_cfg/robot/dual_x5.yml",
                     "env_cfg/camera/camera_config.yml", "task/RoboDojo/config/_task.yml",
                     "src/eval_client/main.py", "src/eval_client/eval_env.py", "env/seed_manager/seed_manager.py"]
    source = dict(robodojo=git_state(robodojo), xpolicylab=git_state(robodojo / "XPolicyLab"),
                  isaaclab=git_state(robodojo / "third_party/IsaacLab"), curobo=git_state(robodojo / "third_party/curobo"),
                  files={p: sha256(robodojo / p) for p in version_paths})
    payload = dict(created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), root=str(robodojo),
                   environment=source, counts=native["counts"], tasks=records,
                   test_cases=len(test), development_cases=len(development),
                   excluded_development_cases=len(overlap),
                   split_rule="native first N saved layouts for final test; extra saved layouts with different serialized hashes for development; no modulo remapping",
                   limitations=["layout hashes identify serialized initial layouts, not complete settled physics state",
                                "standard and random are configurations, not 54 different canonical task goals"])
    destination = root / "manifests"
    destination.mkdir(parents=True, exist_ok=True)
    outputs = {"inventory.json": payload, "test-all.json": dict(split="test", cases=test),
               "development-all.json": dict(split="development", cases=development),
               "excluded-development-overlap.json": dict(reason="Serialized layout duplicates a test layout", cases=overlap),
               "pilot.json": dict(split="test", purpose="interface pilot, not final ranking",
                                  cases=[c for c in test if c["task"] in PILOT_TASKS and c["layout_id"] < 3]),
               "calibration.json": dict(split="calibration", purpose="infrastructure only; excluded from main results",
                                        cases=[c for c in test if c["task"] == "general_pickup" and c["layout_id"] == 0])}
    for name, data in outputs.items():
        (destination / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return payload
