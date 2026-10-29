import re

import pytest

from fplp.conditions import TASK_NEED, TaskNeed
from fplp.signals.formats import Extent, SignalForm
from fplp.tasks.specs import build_episode


@pytest.mark.parametrize("task_type", list(TASK_NEED))
@pytest.mark.parametrize("extent", list(Extent))
def test_payload_identical_across_forms(make_condition, task_type, extent):
    specs = [build_episode(make_condition(f.value, task_type, item=3, extent=extent)) for f in SignalForm]
    assert all(s.rows == specs[0].rows and s.gold == specs[0].gold for s in specs)


@pytest.mark.parametrize("task_type", list(TASK_NEED))
def test_extent_sizes(make_condition, task_type):
    size = {e: len(build_episode(make_condition("none", task_type, 3, extent=e)).rows) for e in Extent}
    assert size[Extent.LAST_FULL] == 20
    assert size[Extent.LAST_SHORT] < 20
    assert size[Extent.MORE_FULL] == size[Extent.MORE_SHORT] > 40


@pytest.mark.parametrize("item", range(10))
def test_answer_placement(make_condition, item):
    limit = 20
    exists = build_episode(make_condition("has_more", "exists", item, variant=item % 2))
    cheap = [i for i, r in enumerate(exists.rows) if r["price"] < 15]
    if item % 2 == 0:
        assert exists.gold.value == "yes" and len(cheap) == 1 and cheap[0] >= limit
    else:
        assert exists.gold.value == "no" and not cheap

    lookup = build_episode(make_condition("has_more", "lookup", item))
    hits = [i for i, r in enumerate(lookup.rows) if r["amount"] == lookup.gold.value]
    assert hits and hits[0] < limit // 2

    for task, key, value in [("filtered_count", "status", "refunded"),
                             ("count_out_of_stock", "in_stock", False),
                             ("count_high_priority", "priority", "high")]:
        spec = build_episode(make_condition("has_more", task, item))
        marked = [i for i, r in enumerate(spec.rows) if r[key] == value]
        assert len(marked) == spec.gold.value
        assert min(marked) < limit and max(marked) >= limit

    oldest = build_episode(make_condition("has_more", "oldest_date", item))
    assert oldest.gold.value == oldest.rows[-1]["date"] and len(oldest.rows) > limit

    name_one = build_episode(make_condition("has_more", "name_one", item))
    assert sum(r["in_stock"] for r in name_one.rows[: limit // 2]) >= 2


@pytest.mark.parametrize("task_type", [t for t, n in TASK_NEED.items() if n is TaskNeed.NEEDS_ALL])
def test_phrasing(make_condition, task_type):
    neutral = build_episode(make_condition("none", task_type, 0)).question
    explicit = build_episode(make_condition("none", task_type, 0, phrasing="explicit")).question
    assert not re.search(r"\b(all|total)\b", neutral, re.IGNORECASE)
    assert re.search(r"\ball\b", explicit, re.IGNORECASE)


def test_tools_carry_two_task_types(make_condition):
    tools = {}
    for task in TASK_NEED:
        tools.setdefault(build_episode(make_condition("none", task, 0)).target_tool, set()).add(task)
    assert all(len(tasks) >= 2 for tasks in tools.values())


@pytest.mark.parametrize("config", ["pilot", "main"])
def test_exists_answers_balance_in_every_cell(config):
    import collections
    from pathlib import Path

    import yaml

    from fplp.conditions import build_conditions

    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "runs" / f"{config}.yaml").read_text())
    cells = collections.defaultdict(collections.Counter)
    for c in build_conditions(cfg):
        if c.task_type == "exists" and c.replicate == 0:
            cells[(c.arm, c.signal_form, c.extent, c.conflict, c.answer_format)][build_episode(c).gold.value] += 1
    assert cells
    for counts in cells.values():
        assert abs(counts["yes"] - counts["no"]) <= 1


def test_confirmatory_runs_share_no_episode_with_protocol_checks():
    from pathlib import Path

    import yaml

    from fplp.conditions import build_conditions

    runs = Path(__file__).resolve().parents[1] / "configs" / "runs"

    def ids(name):  # a condition's identity fixes its items, so equal identities mean reused items
        cfg = yaml.safe_load((runs / f"{name}.yaml").read_text())
        return {(m, c.identity()) for m in cfg["models"] for c in build_conditions(cfg)}

    checks = ids("check") | ids("check-wide") | ids("capcheck") | ids("nemotron-check")
    for name in ["pilot", "main", "secondary"]:
        assert not ids(name) & checks, name


def test_retest_conditions_are_a_seeded_tenth_and_bypass_the_replicate_cap():
    from fplp.conditions import build_conditions, planned

    cfg = {"signal_forms": ["none", "has_more"], "task_need": ["needs_all"], "items_per_cell": 50, "seed": 1,
           "retest_fraction": 0.1}
    cs = build_conditions(cfg)
    retests = [c for c in cs if c.arm == "retest"]
    assert len(retests) == 10 and all(c.replicate == 1 for c in retests)
    assert [c.identity() for c in build_conditions(cfg) if c.arm == "retest"] == [c.identity() for c in retests]
    capped = {"name": "m", "provider": "scripted", "replicates": 1}
    kept = [c for _, c in planned(capped, cs, 12)]
    assert sum(c.arm == "retest" for c in kept) == 10 and len(kept) == 110   # first runs plus the retests
