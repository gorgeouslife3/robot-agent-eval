# Sources and attribution

The MIT license in this repository applies to its original evaluation, adapter, analysis, documentation, and locally authored skill material. It does not replace upstream licenses for source snapshots, models, simulator assets, or datasets. External source trees and weights are downloaded separately and are ignored by Git.

| Component | Upstream | Identity |
| --- | --- | --- |
| RoboDojo simulator and tasks | https://github.com/RoboDojo-Benchmark/RoboDojo | Historical native identities and file hashes in `manifests/inventory.json` |
| Astra native control / π₀.₅ bridge | https://github.com/anonymous-report-421/eval-of-gpt-6-astra-as-policy | `source-lock.json`: `astra_policy` |
| RPent | https://github.com/RLinf/RPent | `source-lock.json`: `rpent` |
| Graph as Policy | https://github.com/graph-robots/graph-as-policy | `source-lock.json`: `gap` |
| PhyAgentOS | https://github.com/PhyAgentOS/PhyAgentOS-core | `source-lock.json`: `phyagentos` |

The separately downloaded PhyAgentOS RoboDojo skill 0.2.1 is identified in `runtime-source-lock.json`. Its bundled third-party notices include components whose license has not been verified; the artifact is not redistributed by this repository.

Other surveyed methods and source locations are listed in `robot_agent_eval/catalog.py` and `source-lock.json`. Downloading a source repository does not mean it has a working adapter or has completed evaluation. Review each upstream project's license and model access terms before use or redistribution.

The local shovel skills are experimental task guidance authored for this workspace; the PhyAgentOS variant is not an official PhyAgentOS skill. They contain no saved layout coordinates or successful action sequences.
