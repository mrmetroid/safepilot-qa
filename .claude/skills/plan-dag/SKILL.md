---
name: plan-dag
description: Draw a repository's plan as a dependency graph (a DAG) and publish it as a private Artifact in the owner's house style. The page shows phases as columns of steps (done, next, planned), what is waiting on the owner, the open deferrals, and the 1.0 milestone. It reads docs/PLAN.md, either YAML `phases:` with `deliverables:` and a `deferrals:` registry, or a Markdown checklist of stages, together with docs/HANDOFF.md. Use it whenever the user asks to see, draw, map, visualise or refresh the plan, roadmap, DAG, dependency graph, progress or "where the project stands" for a repo that keeps a PLAN.md or HANDOFF.md, even if they never say "DAG" or "graph".
---

# Plan DAG

The page is one picture of where a project stands:
- **the plan as columns of steps:** read top to bottom within a phase, and phase to phase from left to right;
- **above it,** a row of summary tiles;
- **beside the step that waits,** what the owner owes;
- **in their own boxes,** the deferrals before and after the milestone;
- **below it,** what is left, in order.

The styling is fixed on purpose: the owner chose it, and every repo's page should look the same. The bundled script draws the page. Your job is the judgement the script cannot make: short titles, what is owed, and the milestone.

A repo this fits keeps its status in `docs/PLAN.md` (or `docs/plan.md`, `PLAN.md`), in one of two forms:
- **YAML:** fenced ```yaml blocks with `phases:`, each phase holding `deliverables:` with `id`, `title` and `status`, and a `deferrals:` registry whose records give `item`, `severity`, `expiry` and `to`;
- **a Markdown checklist:** `- [x] **S0 Title**` for a stage, with indented `- [ ] S0.1 Step` lines under it.

The statuses are `[ ]`, `[~]`, `[x]` and `[x*]`. The current state is in `docs/HANDOFF.md`. If the repo has neither form, say so and stop: the page must never invent a plan.

Either form may assign work to team members:
- **YAML:** `assignee: <handle>` (or a list of handles) on a phase or a deliverable;
- **checklist:** one or more trailing `@handle` on a stage or step line.

A step without its own assignee belongs to its phase's assignee. When any phase or step is assigned, the page shows it:
- the step box shows the step's own `@handle` after its id;
- the column head shows the phase's;
- "What's left" names the owner of every open step, or "unassigned";
- an "Unassigned" tile counts the open steps that nobody owns.

Assignees come only from the plan; the page never invents one. Quote YAML strings that contain ` #` (for example `"PR #4"`), because YAML reads the rest as a comment.

## Steps

1. **Inspect the plan.** The first run fetches PyYAML once:
   ```sh
   uv run ~/.claude/skills/plan-dag/scripts/plan_dag.py inspect <repo>
   ```
   It prints JSON:
   - every phase, with its steps and statuses;
   - every deferral, with its registry index and group: `pre` (open before the milestone: `pre-*`, `blocking-*`), `post`, or `dropped`;
   - the commit and whether the tree has uncommitted changes;
   - `next_guess`.

2. **Read what needs judgement:**
   - `docs/HANDOFF.md`:
     - the Current Step;
     - everything put to the owner that is not yet answered;
     - whether the next step waits for a go-ahead;
     - the Next Prompt;
   - the repo's `CLAUDE.md`:
     - the owner's name;
     - what the milestone is (for example "1.0 is the first version that …");
     - what the deferral severities mean;
   - the prose of `PLAN.md`.

   Draw only what these documents state. The page is a view of the plan, so it never adds a dependency, a date or a step that the plan does not have. When the documents disagree, the plan owns status, and the handoff owns what is waiting.

3. **Write the overlay** to the session's scratchpad, never inside the repo. The page is a view, not a tracked file, and some repos forbid tracked files that name other projects. [references/overlay.md](references/overlay.md) gives every key, with an example. The essentials:
   - **`short`:** a title of at most about 50 characters for every step, in the plan's own words. Shorten a title; never reinterpret it;
   - **`owner`, `next`, `owed`:** the owed items come from the handoff's open questions, each one at most 32 characters;
   - **`milestone`:** where the milestone sits, and what it needs;
   - **`deferral_labels`:** at most 24 characters each. The script appends the due step or month;
   - **`why`:** one plain sentence for each step left, and only where the documents give a reason.

4. **Render the page:**
   ```sh
   uv run ~/.claude/skills/plan-dag/scripts/plan_dag.py render <repo> --overlay <overlay.json> --out <scratchpad>/<name>-plan.html
   ```
   The script prints one line of counts, then a warning for every box it had to guess at (a step with no short title, a deferral with no label). Fill the overlay until no warnings remain.

5. **Look once, if you can.** Take one screenshot of the local file with headless Chrome, or one Artifact preview:
   ```sh
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars --window-size=1280,1100 --virtual-time-budget=4000 --screenshot=<png> file://<html>
   ```
   Make one pass of fixes for text that is cut or overlaps, then publish. Do not loop.

6. **Publish with the Artifact tool:**
   - Load `artifact-design` first, as the tool requires. The page already meets its contract (a title, colour tokens with dark mode, the gutter, Google Fonts only), so keep its styling.
   - Keep one link per repo. List the person's artifacts. If one has the same title, read it, then publish to its `url`: an update in place keeps the link and its history. Otherwise, publish a new one with `icon: "map"`.
   - Give a one-sentence description, such as "<Project>'s plan as a dependency graph, from PLAN.md and HANDOFF.md at <commit>."
   - The page is private, so do not share it.

7. **Report:**
   - the link;
   - the counts from the render line;
   - what is owed;
   - anything the page cannot show, such as uncommitted plan changes, which the stamp names, or a deferral whose due step is not on the page.

## How the script draws

These rules decide where things go, so you can predict the page and fix it from the overlay:
- **Columns:** phases up to the last one with any progress are columns. More than five fold the oldest into one "Earlier phases" column. Later phases stack in one "After <milestone>" column.
- **Steps a spec has not written yet:** a later phase with a single step (its spec) gets a dashed ghost box, "<n>.x … written into its spec". A checklist stage with no steps is drawn as one box.
- **Arrows:**
  - each grey arrow means "comes after": steps within a phase, then the last step of a phase into the next phase;
  - an amber arrow ties what is owed to the next step;
  - a dashed amber arrow ties each open deferral to the step it is due at, or to the milestone.
- **Tiles:** steps done, the phase in progress, next, what is waiting on the owner, and the open deferrals.
- **Next:** the overlay's `next` wins. Without it, the first step `[~]`, or else the first `[ ]`. Set `next` whenever the handoff says the next step waits, for example when a phase stays `[~]` for the owner's approvals even though all its steps are done.
