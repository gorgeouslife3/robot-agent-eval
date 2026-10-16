# Framework pilot

Work in `/path/to/robot-agent-eval`. The simulator and all controllers are
started by the runner. Do not launch simultaneous trials: Isaac Sim, π0.5 and
SAM3 share one GPU. Controllers receive public sensors and robot state; official
scoring stays outside their tool context. Credentials stay in `secrets/`.

```bash
/path/to/robodojo-env/bin/python -m robot_agent_eval.runner --method rpent_astra --manifest manifests/pilot.json --task general_pickup --layout 1 --config configs/model.pilot.json
/path/to/robodojo-env/bin/python -m robot_agent_eval.runner --method gap_astra --manifest manifests/pilot.json --task general_pickup --layout 1 --config configs/model.pilot.json
/path/to/robodojo-env/bin/python -m robot_agent_eval.runner --method phyagentos_official_astra --manifest manifests/pilot.json --task general_pickup --layout 1 --config configs/model.pilot.json
/path/to/robodojo-env/bin/python -m robot_agent_eval.runner --method phyagentos_custom_astra --manifest manifests/pilot.json --task general_pickup --layout 1 --config configs/model.pilot.json
```

`configs/model.gap-pilot.json` changes only GaP's per-stage tool-use cap from the
source default 6 to 12. This is a separate development condition; it retains the
same overall 60 requests, 2 million tokens and 1200-second controller budget.

Generate reports without model calls:

```bash
.venvs/frameworks/bin/python -m robot_agent_eval.compare_frameworks
.venvs/frameworks/bin/python -m robot_agent_eval.aggregate
PYTHONPATH=source-snapshots/phyagentos .venvs/frameworks/bin/python -m unittest discover -s tests -v
```

The comparison retains every attempt and separates native terminal outcomes,
budget failures, graph generation failures, initialization and transport faults.
The report links exact text inputs, source identities, tool calls, graph topology,
skill activation and recorded action order. `result.before-framework-accounting-fix.json`
preserves older accounting before executed-step recovery and transport classification.

These are local ports of framework components, not claims of full official
reproduction. RPent uses an added Responses planner with its original toolkit;
GaP semantic checkpoints are off because `world_snapshot` is unavailable;
PhyAgentOS uses a local HTTP transport instead of Dora. Its official and custom
conditions expose different control tools. Read the Chinese report for details.

This layout helped develop the custom skills. Freeze adapter/config/skill hashes
before expanding to unseen layouts. A single scene with changing adapters cannot
estimate a stable success rate or isolate which architectural choice helps.
