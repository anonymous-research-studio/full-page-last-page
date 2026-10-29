"""The Anthropic client against a fake Messages API: request shape, the tool loop, the forced final
answer at the cap, and refusals. No network calls."""

import copy
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("anthropic")

from fplp.agents.anthropic_client import AnthropicClient
from fplp.episode import LIMIT_NOTICE, SYSTEM_PROMPT, run_episode
from fplp.tasks.specs import build_episode


def response(content, stop="tool_use", tokens_in=100, tokens_out=20, cache_write=None, cache_read=None):
    return NS(content=content, stop_reason=stop, usage=NS(input_tokens=tokens_in, output_tokens=tokens_out,
                                                          cache_creation_input_tokens=cache_write,
                                                          cache_read_input_tokens=cache_read))


def tool_use(id_, spec, **extra_args):
    return NS(type="tool_use", id=id_, name=spec.target_tool, input={**spec.target_args, **extra_args})


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.script.pop(0)


def make(monkeypatch, script, **kwargs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = AnthropicClient("claude-test", "model-under-test", **kwargs)
    fake = FakeMessages(script)
    client.client = NS(messages=fake)
    return client, fake


@pytest.fixture
def spec(make_condition):
    return build_episode(make_condition("has_more", "filtered_count", 0))


def test_tool_loop_request_shape(monkeypatch, spec):
    thinking = NS(type="thinking", thinking="check page 1", signature="sig")
    client, fake = make(monkeypatch, [
        response([thinking, tool_use("tu1", spec)]),
        response([NS(type="text", text="FINAL ANSWER: 3")], stop="end_turn"),
    ], effort="high")
    rec = run_episode(client, spec, max_tool_calls=12)

    first = fake.calls[0]
    assert first["model"] == "model-under-test" and first["system"] == SYSTEM_PROMPT
    assert first["messages"] == [{"role": "user", "content": spec.question}]
    assert all("input_schema" in t and "parameters" not in t for t in first["tools"])
    assert first["output_config"] == {"effort": "high"}
    assert "temperature" not in first and "tool_choice" not in first

    second = fake.calls[1]["messages"]
    assert [b.type for b in second[1]["content"]] == ["thinking", "tool_use"]  # reasoning passed back unchanged
    assert second[1]["content"][0].signature == "sig"
    assert second[2]["role"] == "user" and second[2]["content"][0]["tool_use_id"] == "tu1"
    assert second[2]["content"][0]["content"] == rec["calls"][0]["output"]

    assert rec["final_text"] == "FINAL ANSWER: 3" and rec["turns"][0]["reasoning"] == "check page 1"
    assert (rec["tokens_in"], rec["tokens_out"]) == (200, 40) and not rec["empty_reply"]


def test_cap_forces_final_answer_without_tools(monkeypatch, spec):
    client, fake = make(monkeypatch, [
        response([tool_use("tu1", spec)]),
        response([tool_use("tu2", spec, page=2)]),
        response([NS(type="text", text="FINAL ANSWER: 1")], stop="end_turn"),
    ])
    rec = run_episode(client, spec, max_tool_calls=1)
    final = fake.calls[2]
    assert final["tool_choice"] == {"type": "none"}
    last_user = final["messages"][-1]["content"]
    assert last_user[0]["tool_use_id"] == "tu2" and "limit" in last_user[0]["content"]
    assert last_user[-1] == {"type": "text", "text": LIMIT_NOTICE}
    assert rec["hit_cap"] and len(rec["calls"]) == 1


def test_temperature_sent_only_when_set(monkeypatch, spec):
    client, fake = make(monkeypatch, [response([NS(type="text", text="FINAL ANSWER: 0")], stop="end_turn")],
                        temperature=0.0)
    run_episode(client, spec, max_tool_calls=12)
    assert fake.calls[0]["temperature"] == 0.0 and "output_config" not in fake.calls[0]


def test_refusal_ends_episode_and_is_not_an_empty_reply(monkeypatch, spec):
    client, _ = make(monkeypatch, [response([], stop="refusal")])
    rec = run_episode(client, spec, max_tool_calls=12)
    assert rec["stop_reason"] == "refusal" and not rec["empty_reply"] and rec["calls"] == []


def three_turns(spec, **usage):
    return [response([tool_use("tu1", spec)], **usage), response([tool_use("tu2", spec, page=2)], **usage),
            response([NS(type="text", text="FINAL ANSWER: 3")], stop="end_turn", **usage)]


def marks(messages):
    """(message index, block index) of every cache marker in a request."""
    return [(i, j) for i, m in enumerate(messages) if isinstance(m["content"], list)
            for j, b in enumerate(m["content"]) if isinstance(b, dict) and "cache_control" in b]


def unmarked(messages):
    """The prompt as the model reads it: string content as one text block, markers removed."""
    out = []
    for m in messages:
        content = [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else m["content"]
        out.append({**m, "content": [{k: v for k, v in b.items() if k != "cache_control"} if isinstance(b, dict) else b
                                     for b in content]})
    return out


def test_prompt_cache_marks_only_the_last_two_user_messages(monkeypatch, spec):
    client, fake = make(monkeypatch, three_turns(spec), prompt_cache=True)
    run_episode(client, spec, max_tool_calls=12)
    first, third = fake.calls[0]["messages"], fake.calls[2]["messages"]
    assert first[0]["content"] == [{"type": "text", "text": spec.question, "cache_control": {"type": "ephemeral"}}]
    assert marks(third) == [(2, len(third[2]["content"]) - 1), (4, len(third[4]["content"]) - 1)]
    assert all(len(marks(c["messages"])) <= 2 for c in fake.calls)    # the API allows at most four
    assert all(m["role"] == "user" for c in fake.calls for m in [c["messages"][i] for i, _ in marks(c["messages"])])


def test_prompt_cache_leaves_the_prompt_unchanged(monkeypatch, spec):
    cached, fake_cached = make(monkeypatch, three_turns(spec), prompt_cache=True)
    plain, fake_plain = make(monkeypatch, three_turns(spec))
    run_episode(cached, spec, max_tool_calls=12)
    run_episode(plain, spec, max_tool_calls=12)
    assert not any(marks(c["messages"]) for c in fake_plain.calls)    # off unless configured
    for a, b in zip(fake_cached.calls, fake_plain.calls, strict=True):
        assert unmarked(a["messages"]) == unmarked(b["messages"])
        assert {k: v for k, v in a.items() if k != "messages"} == {k: v for k, v in b.items() if k != "messages"}


def test_cache_tokens_are_part_of_tokens_in(monkeypatch, spec):
    client, _ = make(monkeypatch, three_turns(spec, tokens_in=100, cache_write=1_000, cache_read=500), prompt_cache=True)
    rec = run_episode(client, spec, max_tool_calls=12)
    assert (rec["turns"][0]["tokens_in"], rec["turns"][0]["cache_write"], rec["turns"][0]["cache_read"]) == (1_600, 1_000, 500)
    assert (rec["tokens_in"], rec["cache_write"], rec["cache_read"]) == (4_800, 3_000, 1_500)
    client, _ = make(monkeypatch, three_turns(spec))                  # no cache fields reported: zero
    rec = run_episode(client, spec, max_tool_calls=12)
    assert (rec["tokens_in"], rec["cache_write"], rec["cache_read"]) == (300, 0, 0)
