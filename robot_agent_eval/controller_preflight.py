"""Validate original Codex tool-loop startup; does not start a model turn."""
import os
from pathlib import Path
import shutil
import tempfile
from .common import ROOT,source_path,write


def main():
    source_path()
    from hybrid_rollout.robodojo import settings
    settings.PROVIDER='OpenAI'
    from hybrid_rollout.robodojo.skill import run as module
    original=module.agent_config
    def config(audit,agent):
        from .permissions import isolate
        return isolate(original(audit,agent),audit)
    module.agent_config=config
    CodexPolicy=module.CodexPolicy
    home=ROOT/'controller-preflight-home';home.mkdir(mode=0o700,exist_ok=True)
    (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "OpenAI"\n'
        '[model_providers.OpenAI]\nname="OpenAI"\nbase_url="http://127.0.0.1:1/v1"\n'
        'wire_api="responses"\nenv_key="ROBOT_PROXY_TOKEN"\n')
    os.environ.update(CODEX_HOME=str(home),ROBOT_PROXY_TOKEN='no-inference-preflight')
    audit=Path(tempfile.mkdtemp(prefix='controller-preflight-',dir=ROOT))
    worker=None
    try:
        worker=CodexPolicy(audit/'workspace',shutil.which('codex'),timeout=30,method='gpt_only')
        result=dict(ok=True,model=settings.MODEL,thread_id=worker.thread_id,model_requests=0,audit=str(audit))
    except Exception as error:
        result=dict(ok=False,error=str(error),model_requests=0,audit=str(audit))
    finally:
        if worker:worker.close()
    write(ROOT/'controller-preflight.json',result);print(result)


if __name__=='__main__':main()
