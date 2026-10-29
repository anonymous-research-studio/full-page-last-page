import pytest

from fplp.conditions import Condition
from fplp.signals.formats import SignalForm


@pytest.fixture
def make_condition():
    def _make(form="has_more", task_type="filtered_count", item=0, **kw):
        return Condition(signal_form=SignalForm(form), task_type=task_type, item=item, **kw)

    return _make
