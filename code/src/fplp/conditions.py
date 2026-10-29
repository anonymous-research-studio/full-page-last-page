"""Experimental conditions. One Condition fixes everything about an episode except the model."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field, replace
from enum import Enum, StrEnum

from fplp.signals.formats import Conflict, Extent, Placement, SignalForm


class TaskNeed(StrEnum):
    NEEDS_ALL = "needs_all"
    PAGE1_SUFFICIENT = "page1_sufficient"


TASK_NEED = {
    "filtered_count": TaskNeed.NEEDS_ALL,
    "oldest_date": TaskNeed.NEEDS_ALL,
    "exists": TaskNeed.NEEDS_ALL,
    "export_all": TaskNeed.NEEDS_ALL,
    "count_out_of_stock": TaskNeed.NEEDS_ALL,
    "count_high_priority": TaskNeed.NEEDS_ALL,
    "name_one": TaskNeed.PAGE1_SUFFICIENT,
    "lookup": TaskNeed.PAGE1_SUFFICIENT,
}
PHRASINGS = ("neutral", "explicit")
# Tool-description wording when pagination is documented (amendment 2): "default" says a cursor comes
# "from a previous response, when it includes one"; "plain" drops "when it includes one".
DOC_WORDINGS = ("default", "plain")
ANSWER_FORMATS = ("final_line", "completeness")

# A false signal is rendered on the form whose field it falsifies, in the extent where it is false.
CONFLICT_BASE_FORM = {
    Conflict.FALSE_END: SignalForm.HAS_MORE,
    Conflict.FALSE_END_CURSOR: SignalForm.NEXT_CURSOR,
    Conflict.FALSE_TOTAL: SignalForm.TOTAL_COUNT,
    Conflict.FALSE_NOTE: SignalForm.NL_NOTE_JSON,
    Conflict.FALSE_MORE: SignalForm.HAS_MORE,
    Conflict.VISIBLE_TOTAL: SignalForm.HAS_MORE,
    Conflict.VISIBLE_NOTE: SignalForm.NEXT_CURSOR,
}
CONFLICT_EXTENT = {Conflict.FALSE_MORE: Extent.LAST_FULL}  # all others: MORE_FULL


@dataclass(frozen=True)
class Condition:
    signal_form: SignalForm
    task_type: str
    item: int
    extent: Extent = Extent.MORE_FULL
    placement: Placement = Placement.BOTTOM
    conflict: Conflict | None = None
    documented: bool = True
    limit_stated: bool = True
    phrasing: str = "neutral"
    answer_format: str = "final_line"
    page_limit: int = 20
    replicate: int = 0
    seed: int = 0
    # Occurrence of this task type within its cell (item // number of task types); it alternates
    # item-level variants such as the exists task's yes/no, so they balance in every cell.
    variant: int = 0
    # Left out of the condition record (and so of episode ids) at its default, so episodes run before
    # the wording arm existed keep their ids.
    doc_wording: str = "default"
    # Not part of identity: the same settings reached from two arms are one episode.
    arm: str = field(default="core", compare=False)

    def __post_init__(self):
        if self.phrasing not in PHRASINGS:
            raise ValueError(f"phrasing must be one of {PHRASINGS}")
        if self.answer_format not in ANSWER_FORMATS:
            raise ValueError(f"answer_format must be one of {ANSWER_FORMATS}")
        if self.doc_wording not in DOC_WORDINGS:
            raise ValueError(f"doc_wording must be one of {DOC_WORDINGS}")

    @property
    def task_need(self) -> TaskNeed:
        return TASK_NEED[self.task_type]

    @property
    def more_exists(self) -> bool:
        return self.extent in (Extent.MORE_FULL, Extent.MORE_SHORT)

    @property
    def fetch_needed(self) -> bool:
        """Fetching past page 1 is required to answer correctly."""
        return self.more_exists and self.task_need is TaskNeed.NEEDS_ALL

    def to_dict(self) -> dict:
        d = {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(self).items()}
        if d["doc_wording"] == "default":
            del d["doc_wording"]
        d["task_need"] = self.task_need.value
        d["more_exists"] = self.more_exists
        d["fetch_needed"] = self.fetch_needed
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Condition:
        return cls(
            signal_form=SignalForm(d["signal_form"]),
            task_type=d["task_type"],
            item=d["item"],
            extent=Extent(d.get("extent", "more_full")),
            placement=Placement(d["placement"]),
            conflict=Conflict(d["conflict"]) if d.get("conflict") else None,
            documented=d["documented"],
            limit_stated=d.get("limit_stated", True),
            phrasing=d.get("phrasing", "neutral"),
            answer_format=d.get("answer_format", "final_line"),
            page_limit=d["page_limit"],
            replicate=d["replicate"],
            seed=d["seed"],
            variant=d.get("variant", 0),
            doc_wording=d.get("doc_wording", "default"),
            arm=d.get("arm", "core"),
        )

    def identity(self) -> str:
        d = self.to_dict()
        d.pop("arm")
        return json.dumps(d, sort_keys=True)


DEFAULT_MAX_TOOL_CALLS = 12
# Model settings that can change what a model does. They are hashed into every episode id, so a run
# resumed after one of them changes starts fresh instead of mixing settings; prices, request pacing
# and the replicate cap do not change behavior and are left out.
BEHAVIOR_KEYS = ("provider", "model_id", "base_url", "temperature", "seed", "effort", "max_tokens",
                 "extra_body", "policy")


def config_key(model_cfg: dict, max_tool_calls: int) -> str:
    """Short hash of the model's behavior-relevant settings and the episode's tool-call cap."""
    settings = {k: model_cfg[k] for k in BEHAVIOR_KEYS if model_cfg.get(k) is not None}
    settings["max_tool_calls"] = max_tool_calls
    return hashlib.sha1(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]


def episode_id(model_cfg: dict, condition: Condition, max_tool_calls: int) -> str:
    key = f"{model_cfg['name']}|{config_key(model_cfg, max_tool_calls)}|{condition.identity()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def planned(model_cfg: dict, conditions: list[Condition], max_tool_calls: int) -> list[tuple[str, Condition]]:
    """(episode id, condition) for every episode one model runs, after its replicate cap."""
    cap = model_cfg.get("replicates")  # e.g. 1 for models run at temperature 0; retests are always run
    return [(episode_id(model_cfg, c, max_tool_calls), c) for c in conditions
            if cap is None or c.replicate < cap or c.arm == "retest"]


# One-factor arms: config key -> (Condition field, level parser).
ARM_FACTORS = {
    "placement": ("placement", Placement),
    "documentation": ("documented", lambda v: v == "documented"),
    "doc_wording": ("doc_wording", str),
    "limit": ("limit_stated", lambda v: v == "stated"),
    "phrasing": ("phrasing", str),
    "answer_format": ("answer_format", str),
    "extent": ("extent", Extent),
}


def build_conditions(cfg: dict) -> list[Condition]:
    """Expand a run config into conditions: the core cross plus one-factor arms.

    Item i of a task type yields the same rows under every signal form for a given extent,
    which is what holds the payload fixed across forms.
    """
    n_items = cfg.get("items_per_cell")
    if not n_items:
        raise ValueError("items_per_cell must be set in the run config")
    base = {
        "page_limit": cfg.get("page_limit", 20),
        "seed": cfg.get("seed", 0),
        "placement": Placement(cfg.get("default_placement", "bottom")),
    }
    reps = cfg.get("replicates", 1)
    allowed = set(cfg.get("task_types") or TASK_NEED)
    tasks_by_need = {
        need: [t for t, n in TASK_NEED.items() if n is need and t in allowed] for need in TaskNeed
    }
    needs = [TaskNeed(x) for x in cfg["task_need"]]
    out: dict[Condition, None] = {}  # ordered set; a duplicate keeps the arm it was first built under

    def add(arm: str, form: SignalForm, need: TaskNeed, **overrides) -> None:
        tasks = tasks_by_need[need]
        if not tasks:
            return
        for item in range(n_items):
            for rep in range(reps):
                c = Condition(
                    signal_form=form,
                    task_type=tasks[item % len(tasks)],
                    item=item,
                    variant=item // len(tasks),
                    replicate=rep,
                    arm=arm,
                    **{**base, **overrides},
                )
                out.setdefault(c, None)

    # Core: every form under every extent. Off the main extent, only needs-all tasks are informative
    # (page-1-sufficient tasks make any fetch unnecessary everywhere), unless the config says otherwise.
    extents = [Extent(x) for x in cfg.get("extents", ["more_full"])]
    other_needs = [TaskNeed(x) for x in cfg.get("other_extent_task_need", ["needs_all"])]
    for form in cfg["signal_forms"]:
        for extent in extents:
            for need in needs if extent is Extent.MORE_FULL else other_needs:
                add("core", SignalForm(form), need, extent=extent)

    for name, arm in (cfg.get("arms") or {}).items():
        if not arm:
            continue
        arm_needs = [TaskNeed(x) for x in arm.get("task_need", cfg["task_need"])]
        arm_extents = [Extent(x) for x in arm.get("extents", ["more_full"])]
        if name in ("conflict", "visible_conflict"):
            # Answer formats cross the conflict arm, so the completeness field is tested where
            # incomplete answers actually occur.
            for level in arm.get("levels", []):
                cf = Conflict(level)
                for need in arm_needs:
                    for answer_format in arm.get("answer_formats", ["final_line"]):
                        add("conflict", CONFLICT_BASE_FORM[cf], need, conflict=cf,
                            extent=CONFLICT_EXTENT.get(cf, Extent.MORE_FULL), answer_format=answer_format)
            continue
        if name not in ARM_FACTORS:
            raise ValueError(f"unknown arm: {name}")
        field_name, parse = ARM_FACTORS[name]
        forms = arm.get("base_forms") or ([arm["base_form"]] if arm.get("base_form") else [])
        for form in forms:
            for level in arm["levels"]:
                for need in arm_needs:
                    for extent in arm_extents:
                        overrides = {"extent": extent, field_name: parse(level)}
                        add(name, SignalForm(form), need, **overrides)

    conditions = list(out)
    if fraction := cfg.get("retest_fraction"):
        # A seeded random share of the first runs is run a second time (arm "retest", the next
        # replicate index) to measure how reproducible each model's decisions are; every hypothesis
        # test uses the first run only (amendment 1).
        firsts = sorted((c for c in conditions if c.replicate == 0), key=lambda c: c.identity())
        chosen = random.Random(f"{base['seed']}:retest").sample(firsts, round(fraction * len(firsts)))
        conditions += [replace(c, replicate=reps, arm="retest") for c in chosen]
    return conditions
