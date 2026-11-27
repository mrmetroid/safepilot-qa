# The overlay

A JSON object with the judgement the script cannot make. Every key is optional. The script warns about any box it had to guess at.

| Key | What it holds | Without it |
|---|---|---|
| `title` | the page's name, such as "Forest Camp Plan": the project's name plus "Plan" | the repo folder's name, in title case, plus "Plan" |
| `owner` | the owner's first name, from the repo's CLAUDE.md | "the owner" |
| `next` | the step id that is next, as the handoff names it | the first `[~]` step, or else the first `[ ]` |
| `next_label` | the Next tile, such as "2.6 · the answer" | the id and the short title |
| `phase_labels` | `{phase id: "Phase 2 · Advisor"}`: a column head that fits in 26 characters | "Phase N · <title>", cut |
| `short` | `{step id: short title}` for every step, at most about 50 characters, in the plan's own words | the full title, wrapped to two lines and cut |
| `deferred_counts` | `{step id: n}` for an `[x*]` step whose deferral count the handoff or changelog gives | "DONE · DEFERRALS" |
| `owed` | `{"title": "Before 2.6, from Göran", "items": [...], "tile": "2 decisions, the go-ahead"}`: the owner's open questions and approvals, from the handoff only | no owed box |
| `milestone` | `{"id": "1.0", "after": "2.7", "title": "...", "why": "..."}`: the box goes after step `after`. Leave it out when the repo defines no milestone | no milestone box; deferral boxes say "open" and "later" |
| `deferral_labels` | `{registry index: label}`, at most 24 characters; the index comes from `inspect` | the item cut at its first clause |
| `dropped_labels` | `{registry index: label}` for dropped deferrals, such as "task speedups (ruling 14)" | the item cut at its first clause |
| `why` | `{step id: one sentence}` for the list of what is left, only where the documents give a reason | no reason line |
| `caption` | the text under the figure | a generated sentence that explains the arrows and the amber |
| `aria` | the figure's accessible description | a generated summary with counts |
| `sources` | the files the stamp names | the plan and the handoff |
| `ghosts` | `false` turns off the dashed "<n>.x" boxes | `true` |

## Example

```json
{
  "title": "Forest Camp Plan",
  "owner": "Göran",
  "next": "2.6",
  "next_label": "2.6 · the answer",
  "phase_labels": {"phase-0": "Phase 0 · Bootstrap", "phase-2": "Phase 2 · Advisor"},
  "short": {"2.5": "Choosing the move by rollout, and the plan", "2.6": "The answer and forestcamp advise"},
  "deferred_counts": {"2.5": 1},
  "owed": {"title": "Before 2.6, from Göran", "tile": "the margin, the go-ahead",
           "items": ["The near-tie margin for NEXT", "The go-ahead for 2.6"]},
  "milestone": {"id": "1.0", "after": "2.7", "title": "Answers the first milestone question end to end",
                "why": "Needs every pre-1.0 deferral closed."},
  "deferral_labels": {"7": "M4 points a unit", "8": "Historical run time"},
  "dropped_labels": {"6": "task speedups (ruling 14)"},
  "why": {"2.7": "Closes two deferrals: the M4 to M8 points, and the historical run time."}
}
```

## Writing the labels

- **Shorten, never reinterpret.** "The rules model, provenance, the TOML loader, family templates, RuleSource and its fake, the validator" becomes "Rules model, provenance, the TOML loader". Keep the plan's nouns.
- **Owed items are questions or approvals** that the owner has not yet answered, in plain words: "Decision 13's cap values", "The go-ahead for 2.6". Something the agent will do next is not owed.
- **The page reads at a glance,** so use counts, not adjectives: "2 decisions, the go-ahead", not "several pending items".
