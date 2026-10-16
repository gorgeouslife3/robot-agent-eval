---
name: phyagentos-shovel-pickup
description: Pick up the named shovel in RoboDojo with task-bound Forge actions, image evidence, and PhyAgentOS semantic verification. Use with the local dual ARX X5 adapter.
metadata: {"PhyAgentOS":{"always":false,"requires":{"runtime":["phyagentos-shovel-pickup"]}}}
---

# Lift the shovel with auditable Forge actions

The goal is the environment's instruction: lift the named shovel by 10 cm. This
is a local task skill adapted from `robodojo-shovel-pickup`, not an official
PhyAgentOS skill. It contains no saved layout coordinates or successful actions.

Activate this skill as primary, query `robot.observe` context, and create an
AgentTask in `recovery` verification mode. Set the goal and success criterion
to the given lift requirement. Use `robot.delta_action` only through
`forge_tool_start_action` with this task ID. Read each invocation's result before
starting another action; accepted does not mean the arm moved.

`robot.observe` returns measured poses, remaining control steps and three current
RGB file paths. Use the `image` tool in vision mode to inspect the relevant head
and wrist images; the image-analysis model is the same Astra as the planner.
Keep an initial image and the measured pre-grasp hand height for later evidence.
Metric object locations remain estimates from images, not simulator truth.

Choose one arm and a narrow part of the handle. Approach with open fingers,
align their closing direction across the handle, then descend. Near contact use
small changes, usually 5–10 mm when the image supports them. The action tool uses
world-axis position offsets and world x/y/z rotations; it holds the other arm's
measured pose. Each action permits at most 5 cm, 0.35 rad and five control steps.
Use the returned measured pose to assess movement, not the requested offset.

After closing, request a 1–2 cm upward test and inspect the wrist image. A close
command or successful invocation does not prove a grasp. Record a hold only when
the shovel visibly moves with the hand. If it stays on the table, reopen,
re-localize and change grasp depth or alignment; do not repeat the unchanged
close. If it moves with the hand, continue upward while keeping the fingers
closed. Include the test lift in estimated progress toward 10 cm.

Use short action records: stage, visible evidence, intended effect, next check,
and a few facts. Avoid sideways motion or release once a hold is established.
When evidence supports the goal, finalize the AgentTask. The semantic verifier
may request a revision: use `forge_task_begin_revision`, inspect its unmet
criteria and continue within the same episode and remaining budget. Never reset
or start a fresh task to hide a failed grasp. Native evaluation remains the
benchmark verdict; the semantic verdict is recorded separately.
