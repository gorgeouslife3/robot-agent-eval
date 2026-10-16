"""Local dispatch compatibility fixes; upstream snapshots remain unchanged."""
import ast
import inspect
import textwrap


def fix_dispatch_name_collision():
    """Make dispatch target positional-only; forward tool's own `name` unchanged.

    Retains the exact pinned method bodies, including argument validation.
    Both the registry and adapters require the fix because each forwards kwargs.
    """
    from gap_core.tools._registry import ToolRegistry,PythonAdapter,RpcAdapter
    for cls in (ToolRegistry,PythonAdapter,RpcAdapter):
        original=cls.invoke
        if 'name' in [p.name for p in inspect.signature(original).parameters.values()
                if p.kind==inspect.Parameter.POSITIONAL_ONLY]:continue
        source=textwrap.dedent(inspect.getsource(original));tree=ast.parse(source)
        arguments=tree.body[0].args
        assert [a.arg for a in arguments.args[:2]]==['self','name']
        arguments.posonlyargs=arguments.args[:2];arguments.args=arguments.args[2:]
        namespace=dict(original.__globals__)
        exec(compile(ast.fix_missing_locations(tree),'<local-gap-positional-dispatch>','exec'),namespace)
        cls.invoke=namespace['invoke']
