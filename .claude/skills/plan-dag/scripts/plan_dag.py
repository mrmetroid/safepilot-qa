#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2"]
# ///
"""Draw a repository's plan as a dependency-graph page (the plan-dag skill).

    uv run plan_dag.py inspect <repo>                              # the parsed plan, as JSON
    uv run plan_dag.py render <repo> --out page.html [--overlay overlay.json]

The plan is read from docs/PLAN.md (or docs/plan.md, PLAN.md): fenced ```yaml blocks holding
`phases:` (each with `deliverables:`) and `deferrals:`, or else a Markdown checklist of stages and
steps. The overlay is what needs judgement: short titles, what the owner owes, the milestone, and
labels for the deferrals (references/overlay.md). The script draws only orders the plan states:
phases one after another, and each phase's steps one at a time.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

PLAN_FILES = ("docs/PLAN.md", "docs/plan.md", "PLAN.md", "plan.md")
STATUS = {"[x]": "done", "[x*]": "deferred", "[~]": "progress", "[ ]": "planned",
          "x": "done", "x*": "deferred", "~": "progress", " ": "planned", "": "planned"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")

# Geometry, from the reference page: columns of 196 px on a 220 px pitch, boxes 58 px on a 72 px row.
X0, Y0, COL_W, PITCH, BOX_H, ROW = 24, 60, 196, 220, 58, 72
OWED_W, AFTER_W, GAP = 224, 210, 24
CHARS_PER_PX = 1 / 6.15  # Instrument Sans at 12 px, measured on the reference's wrapped titles
MAX_ACTIVE_COLUMNS = 5  # more closed phases than this fold into one "earlier" column


# ---------------------------------------------------------------- the plan

@dataclass
class Step:
    id: str
    title: str
    status: str
    phase: str
    ghost: bool = False
    milestone: bool = False
    assignee: str | None = None  # a team member's handle, without the @


@dataclass
class Phase:
    id: str
    title: str
    status: str
    steps: list[Step] = field(default_factory=list)
    assignee: str | None = None


@dataclass
class Deferral:
    index: int
    item: str
    severity: str
    expiry: str
    to: str
    origin: str

    @property
    def group(self) -> str:
        if self.severity == "dropped" or self.to.startswith("dropped"):
            return "dropped"
        if self.severity.startswith("post"):
            return "post"
        return "pre"  # blocking-*, pre-* and anything else open before the milestone


def _status(raw: Any) -> str:
    text = str(raw if raw is not None else "").strip()
    return STATUS.get(text, STATUS.get(text.strip("[]"), "planned"))


def find_plan(repo: Path) -> Path:
    for name in PLAN_FILES:
        path = repo / name
        if path.is_file():
            real = {p.name.lower(): p for p in path.parent.iterdir()}  # the real case on a case-insensitive disk
            return real.get(path.name.lower(), path)
    raise SystemExit(f"no plan in {repo}: looked for {', '.join(PLAN_FILES)}")


def parse_plan(text: str) -> tuple[list[Phase], list[Deferral]]:
    phases_raw: list[dict[str, Any]] = []
    deferrals_raw: list[dict[str, Any]] = []
    for block in re.findall(r"```ya?ml[^\n]*\n(.*?)```", text, re.S):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError as error:
            print(f"warning: a yaml block does not parse: {error}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            phases_raw += [p for p in data.get("phases") or [] if isinstance(p, dict)]
            deferrals_raw += [d for d in data.get("deferrals") or [] if isinstance(d, dict)]
    phases = [_phase(p) for p in phases_raw] if phases_raw else _checklist(text)
    deferrals = [Deferral(i, str(d.get("item", "")), str(d.get("severity", "")), str(d.get("expiry", "")),
                          str(d.get("to", "")), str(d.get("from", ""))) for i, d in enumerate(deferrals_raw)]
    return phases, deferrals


def _assignee(raw: Any) -> str | None:
    """`assignee: anna`, `assignee: "@anna"` or a list of handles, as one display string without the @."""
    if isinstance(raw, (list, tuple)):
        names = [str(x).strip().lstrip("@") for x in raw if str(x).strip()]
        return ", ".join(names) or None
    text = str(raw or "").strip().lstrip("@")
    return text or None


ASSIGNEE_TAIL = re.compile(r"((?:\s+@[\w.-]+)+)\s*$")


def _split_assignee(title: str) -> tuple[str, str | None]:
    """A checklist title may end in `@anna` or `@anna @ben`."""
    m = ASSIGNEE_TAIL.search(title)
    if not m:
        return title, None
    return title[: m.start()].strip(), ", ".join(h.lstrip("@") for h in m[1].split())


def _phase(raw: dict[str, Any]) -> Phase:
    pid = str(raw.get("id", "?"))
    phase = Phase(pid, str(raw.get("title", pid)), _status(raw.get("status")),
                  assignee=_assignee(raw.get("assignee")))
    for d in raw.get("deliverables") or []:
        if isinstance(d, dict):
            phase.steps.append(Step(str(d.get("id", "?")), str(d.get("title", "")), _status(d.get("status")), pid,
                                    assignee=_assignee(d.get("assignee"))))
    return phase


def _checklist(text: str) -> list[Phase]:
    """A Markdown checklist: `- [x] **S0 Title**` (or `**S1** Title`) for a stage, indented items for steps."""
    phases: list[Phase] = []
    stage = re.compile(r"^- \[(x\*|x|~| )\] \*\*(.+?)\*\*\s*(.*)$")
    step = re.compile(r"^\s+- \[(x\*|x|~| )\] (\S+)\s+(.*)$")
    for line in text.splitlines():
        if m := stage.match(line):
            bold, (rest, who) = m[2].strip(), _split_assignee(m[3].strip())
            pid, _, title = bold.partition(" ")
            phases.append(Phase(pid, (title or rest).strip() or pid, _status(m[1]), assignee=who))
        elif (m := step.match(line)) and phases:
            title, who = _split_assignee(m[3].strip())
            phases[-1].steps.append(Step(m[2], title, _status(m[1]), phases[-1].id, assignee=who))
    return phases


def git_stamp(repo: Path) -> tuple[str, str, bool]:
    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        return done.stdout.strip() if done.returncode == 0 else ""

    found = git("log", "-1", "--format=%h|%cs")
    commit, _, date = found.partition("|")
    return commit or "uncommitted", date, bool(git("status", "--porcelain"))


def guess_next(phases: list[Phase]) -> str | None:
    steps = [s for p in phases for s in p.steps]
    for s in steps:
        if s.status == "progress":
            return s.id
    for s in steps:
        if s.status == "planned":
            return s.id
    return None


def inspect(repo: Path) -> dict[str, Any]:
    plan_path = find_plan(repo)
    phases, deferrals = parse_plan(plan_path.read_text(encoding="utf-8"))
    commit, date, dirty = git_stamp(repo)
    return {
        "plan": str(plan_path.relative_to(repo)),
        "handoff": next((n for n in ("docs/HANDOFF.md", "HANDOFF.md") if (repo / n).is_file()), None),
        "commit": commit, "date": date, "uncommitted_changes": dirty,
        "next_guess": guess_next(phases),
        "phases": [{"id": p.id, "title": p.title, "status": p.status, "assignee": p.assignee,
                    "steps": [{"id": s.id, "title": s.title, "status": s.status, "assignee": s.assignee}
                              for s in p.steps]} for p in phases],
        "deferrals": [{"index": d.index, "group": d.group, "severity": d.severity, "expiry": d.expiry,
                       "from": d.origin, "item": d.item} for d in deferrals],
    }


# ---------------------------------------------------------------- drawing helpers

def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def wrap(text: str, width_px: int, lines: int = 2) -> list[str]:
    limit = max(8, int((width_px - 24) * CHARS_PER_PX))
    words, out, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + (1 if line else 0) <= limit:
            line = f"{line} {word}".strip()
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][: max(1, limit - 1)].rstrip(" ,;:") + "…"
    return out


def clip(text: str, width_px: int, px_per_char: float = 6.15) -> str:
    """Cuts text to fit width_px at about px_per_char (12 px text 6.15, 11.5 px 5.75, 14 px semibold 7.6)."""
    limit = max(8, int((width_px - 24) / px_per_char))
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;:") + "…"


def plain(text: str) -> str:
    """Markdown code spans and emphasis read as plain text in a box."""
    return re.sub(r"[`*]", "", text)


def due(expiry: str) -> str:
    if m := re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", expiry):
        return f"{MONTHS[int(m[2]) - 1]} {m[1]}"
    return expiry


def short_item(item: str) -> str:
    cut = re.split(r" \(|, |: |; | — ", item, maxsplit=1)[0]
    return cut


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    kind: str  # done | deferred | next | progress | planned | ghost | milestone
    step: Step | None = None

    @property
    def mid(self) -> int:
        return self.y + self.h // 2

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


# ---------------------------------------------------------------- the page

class Page:
    def __init__(self, repo: Path, overlay: dict[str, Any]) -> None:
        self.repo, self.o = repo, overlay
        self.info = inspect(repo)
        plan_path = find_plan(repo)
        self.phases, self.deferrals = parse_plan(plan_path.read_text(encoding="utf-8"))
        self.warnings: list[str] = []
        self.owner = str(overlay.get("owner", "the owner"))
        self.next = str(overlay.get("next") or self.info["next_guess"] or "")
        self.short: dict[str, str] = {str(k): str(v) for k, v in (overlay.get("short") or {}).items()}
        self.milestone = overlay.get("milestone") or None
        self.svg: list[str] = []
        self.boxes: dict[str, Box] = {}

    # -- labels
    def assignee_of(self, step: Step) -> str | None:
        """The step's own assignee, else its phase's."""
        if step.assignee:
            return step.assignee
        phase = next((p for p in self.phases if p.id == step.phase), None)
        return phase.assignee if phase else None

    @property
    def uses_assignees(self) -> bool:
        return any(p.assignee or any(s.assignee for s in p.steps) for p in self.phases)

    def title_of(self, step: Step) -> str:
        if step.id in self.short:
            return self.short[step.id]
        if not step.ghost and not step.milestone:
            self.warnings.append(f"no short title for {step.id}: the full title is wrapped and cut")
        return step.title

    def phase_label(self, phase: Phase) -> str:
        labels = self.o.get("phase_labels") or {}
        if phase.id in labels:
            return str(labels[phase.id])
        number = re.sub(r"^phase-", "", phase.id)
        name = "Phase " + number if phase.id.startswith("phase-") else phase.id
        return f"{name} · {phase.title}"

    def tag(self, box: Box) -> tuple[str, str]:
        counts = self.o.get("deferred_counts") or {}
        if box.kind == "deferred":
            n = counts.get(box.step.id) if box.step else None
            text = f"DONE · {n} DEFERRAL{'S' if n != 1 else ''}" if n else "DONE · DEFERRALS"
            return text, "tag-deferred"
        return {"done": ("DONE", "tag-done"), "next": ("NEXT", "tag-next"),
                "progress": ("IN PROGRESS", "tag-next"), "planned": ("PLANNED", "tag-planned"),
                "milestone": ("MILESTONE", "tag-milestone")}.get(box.kind, ("", ""))

    # -- marks
    def node(self, box: Box) -> None:
        step = box.step
        assert step is not None
        full = step.title if not step.ghost else ""
        parts = ["<g>"]
        if full:
            parts.append(f"<title>{esc(step.id)}: {esc(full)}</title>")
        cls = {"done": "n-done", "deferred": "n-deferred", "next": "n-next", "progress": "n-next",
               "planned": "n-planned", "ghost": "n-ghost", "milestone": "n-milestone"}[box.kind]
        parts.append(f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="6" class="{cls}"/>')
        if box.kind == "milestone":
            parts.append(f'<rect x="{box.x + 3}" y="{box.y + 3}" width="{box.w - 6}" height="{box.h - 6}" rx="4" '
                         'class="n-milestone-inner"/>')
        ghost = " t-ghost" if box.kind == "ghost" else ""
        tag, tag_cls = self.tag(box)
        who = ""
        if step.assignee and not step.ghost and not step.milestone:
            # id in mono (~7.6 px a char), the handle in small sans (~5.9 px), the tag in caps (~5.4 px)
            room = box.w - 24 - len(f"{step.id} · ") * 7.6 - (len(tag) * 5.4 + 8 if tag else 0)
            handle = "@" + step.assignee
            fit = max(4, int(room / 5.9))
            handle = handle if len(handle) <= fit else handle[: fit - 1] + "…"
            who = f'<tspan class="t-who"> · {esc(handle)}</tspan>'
        parts.append(f'<text x="{box.x + 12}" y="{box.y + 19}" class="t-id{ghost}">{esc(step.id)}{who}</text>')
        if tag:
            parts.append(f'<text x="{box.right - 12}" y="{box.y + 19}" class="t-tag {tag_cls}" '
                         f'text-anchor="end">{esc(tag)}</text>')
        for i, line in enumerate(wrap(plain(self.title_of(step)), box.w)):
            parts.append(f'<text x="{box.x + 12}" y="{box.y + 36 + 15 * i}" class="t-title{ghost}">{esc(line)}</text>')
        parts.append("</g>")
        self.svg.append("".join(parts))

    def header(self, x: int, head: str, sub: str, dot: str, width: int = COL_W) -> None:
        self.svg.append(f'<text x="{x}" y="22" class="t-head">{esc(clip(plain(head), width + 20, 7.6))}</text>'
                        f'<circle cx="{x + 4}" cy="36" r="4" class="dot-{dot}"/>'
                        f'<text x="{x + 14}" y="40" class="t-sub">{esc(clip(sub, width + 10, 6.0))}</text>')

    def edge(self, d: str, cls: str = "e-chain", marker: str = "m-muted") -> None:
        self.svg.append(f'<path d="{d}" class="{cls}" marker-end="url(#{marker})"/>')

    def listbox(self, x: int, y: int, w: int, head: str, items: list[str], cls: str,
                note: str | None = None) -> Box:
        h = 33 + 15 * len(items)
        out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="{cls}"/>',
               f'<text x="{x + 12}" y="{y + 19}" class="t-boxhead">{esc(clip(plain(head), w, 6.4))}</text>']
        for i, item in enumerate(items):
            out.append(f'<text x="{x + 12}" y="{y + 37 + 15 * i}" class="t-item">· {esc(clip(plain(item), w - 6, 5.75))}</text>')
        self.svg.append("".join(out))
        return Box(x, y, w, h, "list")

    # -- layout
    def kind_of(self, step: Step) -> str:
        if step.id == self.next:
            return "progress" if step.status == "progress" else "next"
        return {"done": "done", "deferred": "deferred", "progress": "progress"}.get(step.status, "planned")

    def columns(self) -> tuple[list[Phase], list[Phase]]:
        last_active = max((i for i, p in enumerate(self.phases)
                           if p.status != "planned" or any(s.status != "planned" for s in p.steps)), default=0)
        active = self.phases[: last_active + 1] if self.phases else []
        return active, self.phases[last_active + 1:]

    def build(self) -> str:
        active, future = self.columns()
        folded: list[Phase] = []
        if len(active) > MAX_ACTIVE_COLUMNS:
            folded, active = active[: len(active) - MAX_ACTIVE_COLUMNS + 1], active[len(active) - MAX_ACTIVE_COLUMNS + 1:]
        x = X0
        column_boxes: list[list[Box]] = []
        if folded:
            boxes = []
            for j, phase in enumerate(folded):
                step = Step(phase.id, phase.title, "done", phase.id)
                self.short.setdefault(phase.id, phase.title)
                box = Box(x, Y0 + j * ROW, COL_W, BOX_H, "done", step)
                boxes.append(box)
                self.boxes[phase.id] = box
            n = sum(len(p.steps) for p in folded)
            self.header(x, "Earlier phases", f"closed · {n} steps", "done")
            column_boxes.append(boxes)
            x += PITCH
        milestone_after = str(self.milestone.get("after", "")) if self.milestone else ""
        for phase in active:
            boxes = []
            y = Y0
            steps = list(phase.steps)
            for step in steps:
                box = Box(x, y, COL_W, BOX_H, self.kind_of(step), step)
                boxes.append(box)
                self.boxes[step.id] = box
                y += ROW
                if step.id == milestone_after:
                    ms = Step(str(self.milestone.get("id", "1.0")), str(self.milestone.get("title", "")), "planned",
                              phase.id, milestone=True)
                    self.short.setdefault(ms.id, ms.title)
                    mbox = Box(x, y, COL_W, BOX_H, "milestone", ms)
                    boxes.append(mbox)
                    self.boxes["@milestone"] = mbox
                    y += ROW
            done = sum(1 for s in steps if s.status in ("done", "deferred"))
            state = {"done": "closed", "deferred": "closed", "progress": "in progress"}.get(phase.status, "planned")
            if state == "planned" and done:
                state = "in progress"
            dot = {"closed": "done", "in progress": "next"}.get(state, "muted")
            who = f" · @{phase.assignee}" if phase.assignee else ""
            self.header(x, self.phase_label(phase), f"{state} · {done} of {len(steps)}{who}", dot)
            column_boxes.append(boxes)
            x += PITCH
        if milestone_after and "@milestone" not in self.boxes:
            self.warnings.append(f"the milestone's step {milestone_after!r} is not in an active column; not drawn")

        # the steps, the chains inside each column, then the gates between columns
        for boxes in column_boxes:
            for box in boxes:
                self.node(box)
        for boxes in column_boxes:
            for a, b in pairwise(boxes):
                cx = a.x + a.w // 2
                self.edge(f"M{cx} {a.bottom} V{b.y - 2}")
        for left, right in pairwise(column_boxes):
            if left and right:
                last, first = left[-1], right[0]
                gx = last.right + GAP // 2
                self.edge(f"M{last.right} {last.mid} H{gx} V{first.mid} H{first.x - 2}", "e-gate")

        last_column = column_boxes[-1] if column_boxes else []
        content_bottom = max((b.bottom for col in column_boxes for b in col), default=Y0)

        # the owed column: what the owner owes, and the deferrals to close before the milestone
        owed = self.o.get("owed") or {}
        owed_items = [str(i) for i in owed.get("items") or []]
        groups = {g: [d for d in self.deferrals if d.group == g] for g in ("pre", "post", "dropped")}
        labels = {str(k): str(v) for k, v in (self.o.get("deferral_labels") or {}).items()}

        def label(d: Deferral) -> str:
            if str(d.index) not in labels:
                self.warnings.append(f"no label for deferral {d.index}: its item is cut at the first clause")
            text = labels.get(str(d.index), short_item(d.item))
            if d.group != "pre" or not d.expiry or " · " in text:
                return text
            when = due(d.expiry)
            return f"{text} · {when}" if when != d.expiry else f"{text} · due {when}"

        ms_id = str(self.milestone.get("id", "1.0")) if self.milestone else None
        owed_x = x
        if owed_items or groups["pre"]:
            subs = [s for s, present in (("answers", owed_items), ("deferrals", groups["pre"])) if present]
            self.header(owed_x, "Owed", " and ".join(subs), "wait", OWED_W)
            y = Y0
            next_box = self.boxes.get(self.next)
            if owed_items:
                y = max(Y0, next_box.y - 10) if next_box else Y0
                head = str(owed.get("title") or f"From {self.owner}")
                box = self.listbox(owed_x, y, OWED_W, head, owed_items, "n-wait")
                if next_box and next_box in last_column:
                    self.edge(f"M{owed_x} {min(box.bottom - 12, max(box.y + 12, next_box.mid))} H{next_box.right + 2}",
                              "e-wait", "m-wait")
                elif next_box and next_box.x > owed_x:
                    self.edge(f"M{box.right} {box.y + 20} H{next_box.x - 2}", "e-wait", "m-wait")
                y = box.bottom + 32
                content_bottom = max(content_bottom, box.bottom)
            if groups["pre"]:
                head = f"Deferrals to close before {ms_id}" if ms_id else "Open deferrals"
                box = self.listbox(owed_x, y, OWED_W, head, [label(d) for d in groups["pre"]], "n-pre")
                targets: list[Box] = []
                for d in groups["pre"]:
                    t = self.boxes.get(d.expiry) or self.boxes.get("@milestone")
                    if t is not None and t in last_column and t not in targets:
                        targets.append(t)
                for t in targets:
                    lo, hi = max(box.y + 12, t.y + 8), min(box.bottom - 5, t.bottom - 8)
                    if lo <= hi:
                        ty = min(hi, max(lo, t.mid))
                        self.edge(f"M{owed_x} {ty} H{t.right + 2}", "e-pre", "m-wait")
                    else:
                        oy = min(box.bottom - 12, max(box.y + 12, t.mid))
                        self.edge(f"M{owed_x} {oy} H{owed_x - GAP // 2 + 2} V{t.mid} H{t.right + 2}", "e-pre", "m-wait")
                content_bottom = max(content_bottom, box.bottom)
            x = owed_x + OWED_W + GAP

        # the after column: later phases stacked, steps a spec will write as ghosts, then later deferrals
        after_x = x
        after_boxes: list[Box] = []
        if future or groups["post"] or groups["dropped"]:
            y = Y0
            for phase in future:
                steps = list(phase.steps)
                if not steps:
                    steps = [Step(phase.id, phase.title, phase.status, phase.id)]
                    self.short.setdefault(phase.id, phase.title)
                for step in steps:
                    box = Box(after_x, y, AFTER_W, BOX_H, self.kind_of(step), step)
                    after_boxes.append(box)
                    self.boxes[step.id] = box
                    y += ROW
                if len(phase.steps) == 1 and self.o.get("ghosts", True):
                    prefix = re.sub(r"\.\w+$", "", phase.steps[0].id)
                    ghost = Step(f"{prefix}.x", f"{self.phase_label(phase).split(' · ')[0]} steps, written into its spec",
                                 "planned", phase.id, ghost=True)
                    self.short.setdefault(ghost.id, ghost.title)
                    box = Box(after_x, y, AFTER_W, BOX_H, "ghost", ghost)
                    after_boxes.append(box)
                    y += ROW
            names = [re.sub(r"^phase-", "", p.id) for p in future]
            head = f"After {ms_id}" if ms_id else "Later"
            span = (f"{names[0]} to {names[-1]}" if len(names) > 3 else
                    " and ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else (names[0] if names else ""))
            sub = ("phases " if all(p.id.startswith("phase-") for p in future) else "") + span
            self.header(after_x, head, f"{sub} · planned" if names else "deferrals", "muted", AFTER_W)
            for box in after_boxes:
                self.node(box)
            for a, b in pairwise(after_boxes):
                dashed = " e-dash" if "ghost" in (a.kind, b.kind) or a.step.phase != b.step.phase else ""  # type: ignore[union-attr]
                cx = a.x + a.w // 2
                self.edge(f"M{cx} {a.bottom} V{b.y - 2}", "e-chain" + dashed)
            post_box = None
            if groups["post"]:
                top = (after_boxes[-1].bottom + 14) if after_boxes else Y0
                head = f"Deferrals after {ms_id}" if ms_id else "Later deferrals"
                post_box = self.listbox(after_x, top, AFTER_W, head, [label(d) for d in groups["post"]], "n-post")
                content_bottom = max(content_bottom, post_box.bottom)
            if groups["dropped"]:
                below = post_box.bottom if post_box else (after_boxes[-1].bottom if after_boxes else Y0)
                dropped = self.o.get("dropped_labels") or {}
                text = "; ".join(str(dropped.get(str(d.index), short_item(d.item))) for d in groups["dropped"])
                self.svg.append(f'<text x="{after_x + 12}" y="{below + 20}" class="t-note">'
                                f'{esc(clip("Dropped: " + text, AFTER_W * 2))}</text>')
                content_bottom = max(content_bottom, below + 24)
            content_bottom = max(content_bottom, max((b.bottom for b in after_boxes), default=Y0))
            # the gate from the last active column into the after column, routed under the owed column
            if last_column and after_boxes:
                last = last_column[-1]
                route = max(b.bottom for b in last_column) + 20
                if owed_x != after_x:
                    route = max(route, content_bottom + 20) if content_bottom < route + 200 else route
                cx = last.x + last.w // 2
                gx = after_x - GAP // 2
                self.edge(f"M{cx} {last.bottom} V{route} H{gx} V{after_boxes[0].mid} H{after_x - 2}", "e-gate")
                if post_box:
                    self.edge(f"M{gx} {post_box.mid} H{after_x - 2}", "e-post")
                content_bottom = max(content_bottom, route)
            x = after_x + AFTER_W + GAP
        width = x if x > X0 else X0 + COL_W + GAP
        height = content_bottom + 18
        self.size = (width, height)
        self.groups = groups
        self.after_boxes = after_boxes
        self.active = active
        self.future = future
        return "".join(self.svg)

    # -- the HTML around it
    def render(self) -> str:
        marks = self.build()
        width, height = self.size
        info = self.info
        title = str(self.o.get("title") or f"{self.repo.name.replace('-', ' ').title()} Plan")
        steps = [s for p in self.phases for s in p.steps]
        done = sum(1 for s in steps if s.status in ("done", "deferred"))
        progress = next((p for p in self.phases if p.status == "progress"), None)
        next_step = next((s for s in steps if s.id == self.next), None)
        ms_id = str(self.milestone.get("id")) if self.milestone else None
        pre, post = len(self.groups["pre"]), len(self.groups["post"])
        owed = self.o.get("owed") or {}

        tiles = [("Steps done", f"{done} of {len(steps)}", "done")]
        if progress:
            pd = sum(1 for s in progress.steps if s.status in ("done", "deferred"))
            tiles.append(("In progress", f"{self.phase_label(progress).split(' · ')[0]} · {pd} of {len(progress.steps)}",
                          "next"))
        if next_step:
            tiles.append(("Next", str(self.o.get("next_label") or f"{next_step.id} · {self.title_of(next_step)}"),
                          "next"))
        if owed.get("tile") or owed.get("items"):
            tiles.append((f"Waiting on {self.owner}", str(owed.get("tile") or f"{len(owed['items'])} items"), "wait"))
        if self.deferrals:
            value = f"{pre} before {ms_id} · {post} after" if ms_id else f"{pre + post} open"
            tiles.append(("Deferrals open", value, ""))
        if self.uses_assignees:
            open_steps = [s for s in steps if s.status not in ("done", "deferred")]
            unassigned = sum(1 for s in open_steps if not self.assignee_of(s))
            tiles.append(("Unassigned", f"{unassigned} of {len(open_steps)} open steps", "wait" if unassigned else ""))

        kinds = {b.kind for b in self.boxes.values()} | {b.kind for b in self.after_boxes}
        legend = [("done", "Done", kinds & {"done", "deferred"}), ("next", "Next up", kinds & {"next", "progress"}),
                  ("", "Planned", kinds & {"planned"}), ("milestone", "Milestone", kinds & {"milestone"}),
                  ("wait", f"Waiting on {self.owner}", owed.get("items")),
                  ("pre", f"Deferral to close before {ms_id}" if ms_id else "Open deferral", pre),
                  ("post", f"Deferral after {ms_id}" if ms_id else "Later deferral", post)]

        stamp_sources = self.o.get("sources") or [s for s in (info["plan"], info["handoff"]) if s]
        sources = " and ".join(f"<code>{esc(s)}</code>" for s in stamp_sources)
        when = info["date"]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when or ""):
            y, m, d = when.split("-")
            when = f"{int(d)} {MONTH_NAMES[int(m) - 1]} {y}"
        dirty = ", with uncommitted changes" if info["uncommitted_changes"] else ""
        stamp = f"From {sources} at commit <code>{esc(info['commit'])}</code>{dirty}, {esc(when)}."

        caption = self.o.get("caption")
        if not caption:
            caption = ('Every grey arrow means "comes after": the phases run in order, and each phase\'s steps run '
                       'one at a time.')
            if owed.get("items") or pre:
                caption += f" Amber shows what is owed: {self.owner}'s answers, and the deferrals to close"
                caption += f" before {ms_id}." if ms_id else "."
            if any(b.kind == "ghost" for b in self.after_boxes):
                caption += " Dashed boxes are steps a later spec will write."
        aria = self.o.get("aria") or (
            f"The plan as a dependency graph: {done} of {len(steps)} steps done"
            + (f"; {next_step.id} is next" if next_step else "")
            + (f", waiting on {self.owner}" if owed.get("items") else "")
            + (f"; {pre} deferrals to close before {ms_id} and {post} after it" if ms_id and self.deferrals else "")
            + ".")

        why = {str(k): str(v) for k, v in (self.o.get("why") or {}).items()}
        left: list[str] = []
        remaining = [s for s in steps if s.status not in ("done", "deferred")]
        ms_after = str(self.milestone.get("after", "")) if self.milestone else ""
        ordered: list[Step] = []
        for s in remaining:
            ordered.append(s)
            if s.id == ms_after and self.milestone:
                ordered.append(Step(ms_id or "1.0", str(self.milestone.get("title", "")), "planned", "", milestone=True))
        for s in ordered:
            pill = ("milestone" if s.milestone else "next" if s.id == self.next else
                    "in progress" if s.status == "progress" else "planned")
            pill_cls = "next" if pill in ("next", "in progress") else "planned"
            text = plain(s.title if not s.milestone else str(self.milestone.get("title", "")))
            reason = why.get(s.id) or (str(self.milestone.get("why", "")) if s.milestone else "")
            who = ""
            if self.uses_assignees and not s.milestone:
                name = self.assignee_of(s)
                who = (f'<span class="who">@{esc(name)}</span>' if name
                       else '<span class="who none">unassigned</span>')
            left.append(f'<li><span class="id">{esc(s.id)}</span> {esc(text)}<span class="pill {pill_cls}">'
                        f'{esc(pill)}</span>{who}' + (f'<span class="why">{esc(reason)}</span>' if reason else "")
                        + "</li>")

        return TEMPLATE.format(
            title=esc(title), stamp=stamp,
            tiles="".join(f'<li><span class="k">{esc(k)}</span><span class="v {c}">{esc(v)}</span></li>'
                          for k, v, c in tiles),
            legend="".join(f'<li><span class="sw {c}"></span>{esc(t)}</li>' for c, t, present in legend if present),
            width=width, height=height, min_width=max(640, int(width * 0.8)), aria=esc(aria), marks=marks,
            caption=esc(caption),
            left=("<section class=\"left\" aria-labelledby=\"left-h\"><h2 id=\"left-h\">What's left, in order</h2>"
                  f"<ol class=\"steps\">{''.join(left)}</ol></section>") if left else "")


# The Artifact tool wraps the page in its own doctype, head and body, so the page starts at its title.
TEMPLATE = """<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Instrument+Sans:wght@400;500;600;700&display=swap">
<style>
/* One wide figure: the plan as columns of steps, read top to bottom and phase to phase left to right;
   the summary above it, what is left below it. Every colour is a token, redefined for dark mode. */
:root {{
  --bg: #f3f5f2; --surface: #ffffff; --fg: #17201a; --muted: #5a675e; --line: #b6c1b9;
  --done: #2b7644; --done-bg: #e0f0e4; --next: #1d5bc0; --next-bg: #e2ebfb;
  --wait: #955f00; --wait-bg: #fbeed0;
  --font-ui: "Instrument Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #101512; --surface: #18201b; --fg: #e1e8e3; --muted: #97a59b; --line: #3a473e;
    --done: #67c287; --done-bg: #19331f; --next: #82acf7; --next-bg: #172644;
    --wait: #e2a849; --wait-bg: #35280e; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #101512; --surface: #18201b; --fg: #e1e8e3; --muted: #97a59b; --line: #3a473e;
  --done: #67c287; --done-bg: #19331f; --next: #82acf7; --next-bg: #172644;
  --wait: #e2a849; --wait-bg: #35280e; color-scheme: dark;
}}
*, *::before, *::after {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg); font-family: var(--font-ui); font-size: 15px; line-height: 1.5;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 28px 40px;
}}
.wrap {{ max-width: 1200px; margin: 0 auto; display: grid; gap: 22px; min-width: 0; }}
header {{ display: grid; gap: 6px; }}
h1 {{ margin: 0; font-size: 1.65rem; font-weight: 700; letter-spacing: -0.01em; text-wrap: balance; }}
.stamp {{ margin: 0; color: var(--muted); font-size: 0.85rem; }}
code {{ font-family: var(--font-mono); font-size: 0.82rem; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 0; padding: 0; list-style: none; }}
.summary li {{ display: grid; gap: 2px; padding: 10px 14px; border-radius: 8px; background: var(--surface);
  border: 1px solid var(--line); min-width: 0; }}
.summary .k {{ font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }}
.summary .v {{ font-size: 1rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
.summary .v.done {{ color: var(--done); }} .summary .v.next {{ color: var(--next); }} .summary .v.wait {{ color: var(--wait); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 0; padding: 0; list-style: none; font-size: 0.85rem; color: var(--muted); }}
.legend li {{ display: flex; align-items: center; gap: 7px; }}
.sw {{ width: 22px; height: 14px; border-radius: 3px; border: 1.5px solid var(--line); background: var(--surface); flex: none; }}
.sw.done {{ background: var(--done-bg); border-color: var(--done); }}
.sw.next {{ background: var(--next-bg); border-color: var(--next); border-width: 2px; }}
.sw.wait {{ background: var(--wait-bg); border-color: var(--wait); }}
.sw.pre {{ border-style: dashed; border-color: var(--wait); }}
.sw.post {{ border-style: dashed; border-color: var(--muted); }}
.sw.milestone {{ outline: 1.5px solid var(--fg); outline-offset: -4px; border-color: var(--fg); }}
figure {{ margin: 0; display: grid; gap: 10px; min-width: 0; }}
.scroller {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 10px; }}
svg.dag {{ display: block; width: 100%; height: auto; margin: 0 auto; }}
figcaption {{ color: var(--muted); font-size: 0.88rem; max-width: 70ch; }}
.t-head {{ font: 600 14px var(--font-ui); fill: var(--fg); }}
.t-sub {{ font: 500 11.5px var(--font-ui); fill: var(--muted); }}
.t-id {{ font: 600 12.5px var(--font-mono); fill: var(--fg); }}
.t-who {{ font: 500 11px var(--font-ui); fill: var(--muted); }}
.t-tag {{ font: 600 9.5px var(--font-ui); letter-spacing: 0.08em; }}
.t-title {{ font: 400 12px var(--font-ui); fill: var(--fg); }}
.t-ghost {{ fill: var(--muted); }}
.t-boxhead {{ font: 600 12px var(--font-ui); fill: var(--fg); }}
.t-item {{ font: 400 11.5px var(--font-ui); fill: var(--fg); }}
.t-note {{ font: 400 11px var(--font-ui); fill: var(--muted); text-decoration: line-through; }}
.tag-done, .tag-deferred {{ fill: var(--done); }} .tag-next {{ fill: var(--next); }}
.tag-planned, .tag-milestone {{ fill: var(--muted); }}
.n-done, .n-deferred {{ fill: var(--done-bg); stroke: var(--done); stroke-width: 1.25; }}
.n-next {{ fill: var(--next-bg); stroke: var(--next); stroke-width: 2.25; }}
.n-planned {{ fill: var(--surface); stroke: var(--line); stroke-width: 1.25; }}
.n-ghost {{ fill: none; stroke: var(--line); stroke-width: 1.25; stroke-dasharray: 4 4; }}
.n-milestone {{ fill: var(--surface); stroke: var(--fg); stroke-width: 1.25; }}
.n-milestone-inner {{ fill: none; stroke: var(--fg); stroke-width: 0.75; }}
.n-wait {{ fill: var(--wait-bg); stroke: var(--wait); stroke-width: 1.5; }}
.n-pre {{ fill: var(--surface); stroke: var(--wait); stroke-width: 1.5; stroke-dasharray: 5 4; }}
.n-post {{ fill: var(--surface); stroke: var(--muted); stroke-width: 1.25; stroke-dasharray: 5 4; }}
.dot-done {{ fill: var(--done); }} .dot-next {{ fill: var(--next); }} .dot-wait {{ fill: var(--wait); }} .dot-muted {{ fill: var(--muted); }}
.e-chain, .e-gate, .e-post {{ fill: none; stroke: var(--muted); stroke-width: 1.4; }}
.e-dash, .e-post {{ stroke-dasharray: 4 4; }}
.e-wait {{ fill: none; stroke: var(--wait); stroke-width: 1.6; }}
.e-pre {{ fill: none; stroke: var(--wait); stroke-width: 1.4; stroke-dasharray: 5 4; }}
.mk-muted {{ fill: var(--muted); }} .mk-wait {{ fill: var(--wait); }}
section.left {{ display: grid; gap: 10px; }}
h2 {{ margin: 0; font-size: 1.05rem; font-weight: 600; }}
ol.steps {{ margin: 0; padding-left: 1.4em; display: grid; gap: 8px; max-width: 78ch; }}
ol.steps li {{ padding-left: 4px; }}
ol.steps .id {{ font-family: var(--font-mono); font-weight: 600; font-size: 0.9rem; }}
ol.steps .why {{ display: block; color: var(--muted); font-size: 0.88rem; }}
ol.steps .who {{ margin-left: 0.5rem; font-family: var(--font-mono); font-size: 0.8rem; color: var(--fg); }}
ol.steps .who.none {{ color: var(--muted); font-style: italic; }}
.pill {{ display: inline-block; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 1px 7px; border-radius: 999px; margin-left: 6px; vertical-align: 1px; }}
.pill.next {{ color: var(--next); background: var(--next-bg); }}
.pill.planned {{ color: var(--muted); border: 1px solid var(--line); }}
@media (max-width: 560px) {{ h1 {{ font-size: 1.4rem; }} .summary li {{ flex: 1 1 140px; }} }}
</style>
<div class="wrap">
  <header>
    <h1>{title}</h1>
    <p class="stamp">{stamp}</p>
    <ul class="summary">{tiles}</ul>
  </header>
  <ul class="legend" aria-label="Legend">{legend}</ul>
  <figure>
    <div class="scroller"><svg viewBox="0 0 {width} {height}" style="min-width:{min_width}px;max-width:{width}px" role="img" aria-label="{aria}" class="dag"><defs>
<marker id="m-muted" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" class="mk-muted"/></marker>
<marker id="m-wait" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" class="mk-wait"/></marker>
</defs>{marks}</svg></div>
    <figcaption>{caption}</figcaption>
  </figure>
  {left}
</div>
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect", help="print the parsed plan as JSON")
    p_inspect.add_argument("repo", type=Path)
    p_render = sub.add_parser("render", help="write the page")
    p_render.add_argument("repo", type=Path)
    p_render.add_argument("--overlay", type=Path)
    p_render.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.command == "inspect":
        print(json.dumps(inspect(repo), indent=2, ensure_ascii=False))
        return 0
    overlay = json.loads(args.overlay.read_text(encoding="utf-8")) if args.overlay else {}
    page = Page(repo, overlay)
    text = page.render()
    args.out.write_text(text, encoding="utf-8")
    steps = sum(len(p.steps) for p in page.phases)
    print(f"wrote {args.out}: {len(page.phases)} phases, {steps} steps, {len(page.deferrals)} deferrals, "
          f"{len(page.boxes)} boxes, {page.size[0]}x{page.size[1]}")
    for warning in dict.fromkeys(page.warnings):
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
