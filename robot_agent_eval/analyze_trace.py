"""Measured action timeline and concise public decision excerpts; no hidden reasoning."""
import argparse
import json
from .common import read,write


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=str);a=p.parse_args()
    from pathlib import Path
    run=Path(a.run)
    rows=[json.loads(l) for l in (run/'sim/rpc_timing.jsonl').read_text().splitlines()]
    reset=next(r for r in rows if r['op']=='reset')
    t0=reset['start_monotonic']+reset['elapsed_s']
    points=[(0.,0)]
    for r in rows:
        if r['op']=='chunk_step':points.append((r['start_monotonic']+r['elapsed_s']-t0,r['step_id']))
    history=read(run/'controller/history.json') if (run/'controller/history.json').exists() else []
    summaries=[dict(decision=h['decision'],start_tick=h['start_tick'],end_tick=h['end_tick'],
                    reason=h['response']['reason'],terminal=h.get('terminal'),
                    native_success=h.get('native_success')) for h in history]
    write(run/'public_decision_summary.json',summaries)
    write(run/'action_timeline.json',points)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.2))
    ax.step([x/60 for x,y in points],[y for x,y in points],where='post',color='#166c85',linewidth=2)
    launch=read(run/'launch.json')
    ax.set(xlabel='Elapsed episode wall time (minutes)',ylabel='Executed native control steps',
           title=f"{launch['method']}: {launch['case']['task']} layout {launch['case']['layout_id']}")
    ax.grid(alpha=.2);fig.tight_layout();fig.savefig(run/'action_timeline.png',dpi=180);plt.close(fig)
    print(run/'action_timeline.png')


if __name__=='__main__':main()
