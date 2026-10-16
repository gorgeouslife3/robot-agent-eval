"""Launch framework-owned controllers against the common frozen episode."""
import argparse
from pathlib import Path
from .common import read,write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('method','task','config','output'):p.add_argument('--'+name,required=True,type=Path if name in ('config','output') else str)
    for name in ('sim-port','layout'):p.add_argument('--'+name,type=int,required=True)
    p.add_argument('--policy-port',type=int);p.add_argument('--checkpoint',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False);config=read(args.config)
    try:
        if args.method=='rpent_astra':from .rpent_adapter import run
        elif args.method=='gap_astra':from .gap_adapter import run
        else:from .phyagentos_adapter import run
        run(args,config)
    except Exception as e:
        write(args.output/'failure.json',dict(error_type=type(e).__name__,error=str(e)));raise


if __name__=='__main__':main()
