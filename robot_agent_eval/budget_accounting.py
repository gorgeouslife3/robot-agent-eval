"""Separate native success from completion before the controller deadline."""


def verify_budget_success(native_complete, native_success, process, timing, budget_s):
    if not native_complete or not native_success:
        return False, 'no_valid_native_success', None
    start = process.get('controller_started_monotonic')
    terminal = timing.get('native_terminal_monotonic')
    if start is not None and terminal is not None and budget_s is not None:
        elapsed = terminal - start
        if elapsed < 0:
            return None, 'invalid_clock_order', None
        return elapsed <= budget_s, 'native_terminal_vs_controller_monotonic_deadline', elapsed
    if process.get('status') == 'wall_budget':
        return None, 'legacy_wall_cutoff_without_terminal_clock', None
    return True, 'legacy_controller_returned_before_wall_timeout', None
