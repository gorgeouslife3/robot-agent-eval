"""Scientific accounting regressions, runnable without Isaac or paid calls."""
import tempfile
from pathlib import Path
import unittest
from robot_agent_eval.aggregate import summarize, paired_primary
from robot_agent_eval.common import write
from robot_agent_eval.runner import make_result
from robot_agent_eval.budget_accounting import verify_budget_success


class Accounting(unittest.TestCase):
    def test_native_success_before_deadline_survives_late_observation_cleanup(self):
        value,basis,elapsed=verify_budget_success(True,True,
            {'status':'wall_budget','controller_started_monotonic':1000},
            {'native_terminal_monotonic':1419.5},420)
        self.assertTrue(value);self.assertEqual(elapsed,419.5)

    def test_native_success_after_deadline_is_not_budget_success(self):
        value,_,elapsed=verify_budget_success(True,True,
            {'status':'wall_budget','controller_started_monotonic':1000},
            {'native_terminal_monotonic':1420.2},420)
        self.assertFalse(value);self.assertAlmostEqual(elapsed,420.2)

    def test_legacy_cutoff_native_success_requires_independent_timing_audit(self):
        value,_,elapsed=verify_budget_success(True,True,{'status':'wall_budget'}, {},420)
        self.assertIsNone(value);self.assertIsNone(elapsed)

    def test_unknown_budget_timing_is_reported_separately_from_failures(self):
        known=make_result(self.make_run())
        unknown=dict(known,native_complete=True,native_success=True,success_within_budget=None)
        group=summarize([known,unknown])[0]
        self.assertEqual(group['scored_attempts'],2)
        self.assertEqual(group['budget_scored_attempts'],1)
        self.assertEqual(group['budget_unknown_attempts'],1)
        self.assertEqual(group['success_within_budget'],0.)
        self.assertIsNone(summarize([unknown])[0]['success_within_budget'])

    def test_result_retains_late_native_success_but_does_not_count_budget_success(self):
        p=self.make_run({'valid_for_success_rate':True,'native_success':True,'native_score':1.,
            'status':'native_completed'})
        launch={'method':'astra_direct','split':'test','case':{'case_id':'case1'},'calibration':False,
            'model_config':{'max_episode_wall_s':420}}
        write(p/'launch.json',launch)
        write(p/'process_result.json',{'status':'wall_budget','controller_started_monotonic':1000})
        write(p/'sim/timing.json',{'native_terminal_monotonic':1420.2})
        result=make_result(p)
        self.assertTrue(result['native_success']);self.assertEqual(result['native_score'],1.)
        self.assertFalse(result['success_within_budget'])
        self.assertAlmostEqual(result['terminal_controller_elapsed_s'],420.2)

    def make_run(self,outcome=None,started=True,failure=None):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=Path(self.temp.name)
        write(p/'launch.json',dict(method='astra_direct',split='test',case={'case_id':'case1'},calibration=False))
        write(p/'process_result.json',{'status':'controller_completed'})
        if outcome:write(p/'sim/evaluation_outcome.json',outcome)
        if started:write(p/'sim/reset.json',{})
        if failure:write(p/'controller/failure.json',failure)
        return p

    def test_exit_zero_with_no_native_outcome_is_not_success(self):
        r=make_result(self.make_run(started=False))
        self.assertFalse(r['success_within_budget']);self.assertFalse(r['task_result_eligible'])

    def test_initial_native_success_is_not_terminal_success(self):
        p=self.make_run({'valid_for_success_rate':False,'native_success':True,'status':'incomplete'})
        self.assertFalse(make_result(p)['success_within_budget'])

    def test_token_abort_counts_as_budget_failure_without_fabricated_score(self):
        p=self.make_run({'valid_for_success_rate':False,'native_success':None,'native_score':None},
            failure={'error':'Configured total-token budget reached; stopping this episode'})
        r=make_result(p)
        self.assertEqual(r['status'],'token_budget');self.assertTrue(r['task_result_eligible'])
        self.assertFalse(r['success_within_budget']);self.assertIsNone(r['native_score'])

    def test_native_invalid_layout_is_not_method_failure(self):
        p=self.make_run({'valid_for_success_rate':False,'status':'invalid_native_layout'})
        self.assertFalse(make_result(p)['task_result_eligible'])

    def test_framework_initialization_failure_is_not_robot_failure(self):
        p=self.make_run(failure={'error':'Missing runtime method'})
        write(p/'launch.json',dict(method='rpent_astra',split='test',case={'case_id':'case1'},calibration=False))
        write(p/'process_result.json',{'status':'controller_error'})
        r=make_result(p)
        self.assertEqual(r['status'],'adapter_init_error')
        self.assertFalse(r['task_result_eligible'])

    def test_interrupted_model_request_is_retained_without_invented_tokens(self):
        p=self.make_run()
        (p/'model_request_starts.jsonl').write_text('{"call":1,"phase":"upstream_request_submitted"}\n')
        write(p/'process_result.json',{'status':'wall_budget'})
        r=make_result(p)
        self.assertEqual(r['model_requests'],1)
        self.assertEqual(r['model_requests_finished'],0)
        self.assertEqual(r['model_input_tokens'],0)
        self.assertFalse(r['model_usage_complete'])
        self.assertFalse(r['success_within_budget'])

    def test_explicit_adapter_contract_stop_is_not_robot_failure(self):
        p=self.make_run()
        write(p/'controller/deployment_stop.json',{'status':'adapter_contract_error'})
        r=make_result(p)
        self.assertEqual(r['status'],'adapter_contract_error')
        self.assertFalse(r['task_result_eligible']);self.assertIsNone(r['native_score'])

    def test_transport_loss_retains_executed_steps_without_fabricating_score(self):
        p=self.make_run()
        (p/'sim/rpc_timing.jsonl').write_text('{"op":"public_native_step","step_id":5}\n')
        (p/'controller').mkdir()
        (p/'controller/framework_trace.jsonl').write_text('{"event":"native_rpc_error","error":"RPC connection closed"}\n')
        r=make_result(p)
        self.assertEqual(r['status'],'native_transport_error')
        self.assertEqual(r['native_steps'],5)
        self.assertFalse(r['task_result_eligible']);self.assertIsNone(r['native_score'])

    def test_post_success_controller_error_preserves_native_success(self):
        p=self.make_run({'valid_for_success_rate':True,'native_success':True,
            'native_score':1.,'status':'native_completed'},
            failure={'error':'Configured total-token budget reached; stopping this episode'})
        write(p/'process_result.json',{'status':'controller_error'})
        r=make_result(p)
        self.assertTrue(r['success_within_budget']);self.assertEqual(r['native_score'],1.)
        self.assertEqual(r['status'],'native_completed')

    def test_native_transport_failure_in_original_hybrid_traceback_is_infrastructure(self):
        p=self.make_run(failure={'error':'EOFError: RPC connection closed'})
        write(p/'process_result.json',{'status':'controller_error','simulator_exit_code':-11})
        r=make_result(p)
        self.assertEqual(r['status'],'native_transport_error')
        self.assertFalse(r['task_result_eligible']);self.assertIsNone(r['native_score'])

    def test_retries_and_different_budgets_remain_distinct(self):
        failure=make_result(self.make_run({'valid_for_success_rate':False,'status':'budget_censored'}))
        success=dict(failure,native_complete=True,success_within_budget=True,status='native_completed')
        other=dict(success,model_config_sha256='larger-budget')
        report=summarize([failure,success,other,dict(success,calibration=True)])
        self.assertEqual(len(report),2)
        self.assertEqual(report[0]['total_attempts'],2)
        self.assertEqual(report[0]['success_within_budget'],.5)
        self.assertEqual(report[0]['unique_cases'],1)
        self.assertEqual(len(summarize([dict(success,implementation_sha256='old'),
            dict(success,implementation_sha256='new')])),2)

    def test_paired_comparison_requires_shared_cases_and_keeps_retries(self):
        direct=make_result(self.make_run())
        hybrid=dict(direct,method='astra_hybrid',case_id='other-case')
        policy=dict(direct,method='pi05_only')
        self.assertEqual(paired_primary([direct,hybrid,policy])['matched_cases'],[])
        hybrid['case_id']=direct['case_id']
        paired=paired_primary([direct,dict(direct,success_within_budget=True),hybrid,policy])
        self.assertEqual(len(paired['matched_cases']),1)
        self.assertEqual(len(paired['matched_cases'][0]['attempts']['astra_direct']),2)


if __name__=='__main__':unittest.main()
