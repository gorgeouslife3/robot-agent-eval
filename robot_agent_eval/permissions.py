"""Keep current-episode agent evidence separate from evaluator/other-run data."""
from .common import ROOT, ROBODOJO


def isolate(value, audit):
    rules=value['permissions.rollout_agent.filesystem']
    current_run=audit.parent.parent
    denied=[ROOT/'secrets',ROOT/'manifests',ROBODOJO,current_run/'sim',current_run/'controller/perception_host',
            ROOT/'results',ROOT/'report.zh-CN.md',ROOT/'README.zh-CN.md',
            ROOT.parent.parent/'robot-agent-survey-2026-10-03']
    runs = ROOT / 'runs'
    if runs.is_dir():
        denied.extend(p for p in runs.iterdir() if p.is_dir() and p != current_run)
    rules.update({str(p):'none' for p in denied})
    return value
