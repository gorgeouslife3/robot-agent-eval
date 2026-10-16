"""Pinned GaP dispatcher regression, without paid requests or a simulator."""
import unittest
import sys
from robot_agent_eval.common import ROOT
sys.path.insert(0,str(ROOT/'source-snapshots/gap/gap-core/src'))
from robot_agent_eval.gap_compat import fix_dispatch_name_collision
from gap_core.tools import ToolRegistry
from gap_core.errors import ToolArgumentError


class GaPContracts(unittest.TestCase):
    def test_tool_name_argument_is_forwarded_and_unknown_arguments_still_rejected(self):
        fix_dispatch_name_collision()
        registry=ToolRegistry()
        def capability(ctx,name:str,why:str)->dict:
            return dict(name=name,why=why,context=ctx)
        registry.register_callable('report_missing_capability',capability,requires_ctx=True,summary='Report missing capability')
        result=registry.invoke('report_missing_capability',ctx='context',name='robot.solve_ik',why='reachability')
        self.assertEqual(result,dict(name='robot.solve_ik',why='reachability',context='context'))
        with self.assertRaises(ToolArgumentError):
            registry.invoke('report_missing_capability',ctx='context',name='robot.solve_ik',why='reachability',invented=True)


if __name__=='__main__':unittest.main()
