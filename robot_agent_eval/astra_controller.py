"""Use the original persistent Codex agent with a local provider configuration."""
import os
import sys
from .common import read, source_path


def main():
    source_path()
    from hybrid_rollout.robodojo import settings
    # Provider wiring only. Model, prompts, dynamics, tools and action limits are pinned upstream.
    settings.PROVIDER='OpenAI'
    config=read(os.environ['ROBOT_EVAL_MODEL_CONFIG'])
    assert settings.MODEL==config['model'] and settings.EFFORT==config['reasoning_effort']
    settings.BASE_URL=config['base_url']
    os.environ['CODEX_IMAGE_MAX_EDGE']=str(config['images_max_edge'])
    os.environ['CODEX_MAX_TOTAL_TOKENS']=str(config['max_total_tokens_per_episode'])
    from hybrid_rollout.robodojo.skill import run as module
    original_config=module.agent_config
    def permissions(audit,agent):
        from .permissions import isolate
        return isolate(original_config(audit,agent),audit)
    module.agent_config=permissions
    if config.get('hybrid_perception'):
        from .hybrid_perception import install
        install(module,config)
    if config.get('hybrid_manipulation'):
        from .hybrid_manipulation import install
        install(module,config)
    module.main()


if __name__=='__main__':main()
