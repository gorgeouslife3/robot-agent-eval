"""Summarize every attempt; never select the best retry or discard budget failures."""
from collections import Counter,defaultdict
import math
from statistics import median
from .common import ROOT,read,write


def wilson(successes,count):
    if count==0:return None
    z=1.95996398454;p=successes/count;den=1+z*z/count
    centre=(p+z*z/(2*count))/den
    radius=z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/den
    return [max(0.,centre-radius),min(1.,centre+radius)]


def summarize(rows):
    groups=defaultdict(list)
    for row in rows:
        if row['calibration']:continue
        groups[(row['method'],row.get('model_config_sha256'),row.get('harness_prompt_sha256'),
            row.get('implementation_sha256'),row.get('skill_sha256'))].append(row)
    result=[]
    for (method,budget,prompt,implementation,skill),attempts in groups.items():
        eligible=[r for r in attempts if r['task_result_eligible']]
        budget_known=[r for r in eligible if r['success_within_budget'] is not None]
        success=[r for r in budget_known if r['success_within_budget']]
        times=[r['timing'].get('episode_active_wall_s') for r in success]
        times=[v for v in times if v is not None]
        failed_times=[r['timing'].get('episode_active_wall_s') for r in budget_known if not r['success_within_budget']]
        failed_times=[v for v in failed_times if v is not None]
        all_times=[r['timing'].get('episode_active_wall_s') for r in eligible]
        all_times=[v for v in all_times if v is not None]
        result.append(dict(method=method,model_config_sha256=budget,harness_prompt_sha256=prompt,
            implementation_sha256=implementation,skill_sha256=skill,total_attempts=len(attempts),
            unique_cases=len({r['case_id'] for r in attempts}),scored_attempts=len(eligible),
            budget_scored_attempts=len(budget_known),budget_unknown_attempts=len(eligible)-len(budget_known),
            infrastructure_attempts=len(attempts)-len(eligible),successes=len(success),
            success_within_budget=len(success)/len(budget_known) if budget_known else None,
            interval_95=wilson(len(success),len(budget_known)),
            native_completed=sum(r['native_complete'] for r in eligible),
            status_counts=dict(Counter(r['status'] for r in attempts)),
            success_wall_median_s=median(times) if times else None,
            failed_wall_median_s=median(failed_times) if failed_times else None,
            all_task_wall_median_s=median(all_times) if all_times else None,
            model_calls_total=sum(r['model_requests'] for r in attempts),
            model_usage_complete_all=all(r.get('model_usage_complete',False) for r in attempts),
            input_tokens_total=sum(r['model_input_tokens'] for r in attempts),
            cached_input_tokens_total=sum(r.get('model_cached_input_tokens',0) for r in attempts),
            output_tokens_total=sum(r['model_output_tokens'] for r in attempts)))
    return result


def paired_primary(rows):
    methods=('astra_direct','astra_hybrid','pi05_only')
    groups=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
    for r in rows:
        if (r['method'] in methods and r['task_result_eligible'] and not r['calibration']
                and r['success_within_budget'] is not None):
            groups[r.get('model_config_sha256')][r['case_id']][r['method']].append(r)
    paired=[]
    for budget,cases in groups.items():
        for case,attempts in cases.items():
            if all(m in attempts for m in methods):
                paired.append(dict(case_id=case,model_config_sha256=budget,attempts=dict(attempts)))
    return dict(required_methods=methods,matched_cases=paired,
                rule='Same frozen case and configuration; preserve every eligible attempt, never choose best retry',
                warning='One shared pilot case is not a population success-rate estimate; diagnostic variants excluded')


def main():
    rows=[]
    for path in sorted((ROOT/'runs').glob('*/result.json')):
        row=read(path);row['run_path']=str(path.parent);rows.append(row)
    write(ROOT/'results/attempts.json',rows)
    groups=summarize(rows)
    write(ROOT/'results/summary.json',dict(groups=groups,
        rule='All attempts retained, grouped by method, budget, recorded adapter and skill identity; infrastructure separately counted; no best-of retries',
        model_accounting_warning='Legacy attempts log completed requests only; interrupted request counts/usage may be missing. Totals are recorded values, not a complete provider bill.',
        warning='Interface/budget pilot only; small numbers and different budgets are not a method ranking'))
    write(ROOT/'results/paired-primary.json',paired_primary(rows))
    print(groups)


if __name__=='__main__':main()
