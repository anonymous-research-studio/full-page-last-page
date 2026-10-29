"""The OpenAI-compatible client against a fake Chat Completions API: request shape, the tool loop,
the forced final answer at the cap, refusals, truncation, and the provenance fields. No network calls."""

import copy
import json
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("openai")

from openai.types.chat import ChatCompletion

from fplp.agents.openai_client import OpenAICompatibleClient
from fplp.episode import LIMIT_NOTICE, SYSTEM_PROMPT, run_episode
from fplp.tasks.specs import build_episode

ROUTING = {"provider": {"order": ["crusoe/bf16"], "allow_fallbacks": False}}


def completion(content=None, calls=(), finish="tool_calls", refusal=None):
    tool_calls = [{"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": args}}
                  for i, (name, args) in enumerate(calls)] or None
    return ChatCompletion.model_validate({
        "id": "gen-1", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-120b",
        "system_fingerprint": "fp_1", "provider": "Crusoe",
        "choices": [{"index": 0, "finish_reason": finish, "message": {
            "role": "assistant", "content": content, "refusal": refusal, "tool_calls": tool_calls,
            "reasoning": "check page 1"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    })


def page_call(spec, **extra):
    return spec.target_tool, json.dumps({**spec.target_args, **extra})


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.script.pop(0)


def make(script, **kwargs):
    client = OpenAICompatibleClient("gpt-test", "model-under-test", api_key_env="NO_SUCH_KEY", **kwargs)
    fake = FakeCompletions(script)
    client.client = NS(chat=NS(completions=fake))
    return client, fake


@pytest.fixture
def spec(make_condition):
    return build_episode(make_condition("has_more", "filtered_count", 0))


def test_tool_loop_request_shape(spec):
    client, fake = make([
        completion(calls=[page_call(spec)]),
        completion("FINAL ANSWER: 3", finish="stop"),
    ], temperature=0, seed=0, extra_body=ROUTING)
    rec = run_episode(client, spec, max_tool_calls=12)

    first = fake.calls[0]
    assert first["model"] == "model-under-test" and first["tool_choice"] == "auto"
    assert first["messages"] == [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": spec.question}]
    assert all(t["type"] == "function" and "parameters" in t["function"] for t in first["tools"])
    assert first["temperature"] == 0 and first["seed"] == 0 and first["extra_body"] == ROUTING
    assert "max_tokens" not in first

    # The assistant turn goes back unchanged, followed by one tool message per call.
    second = fake.calls[1]["messages"]
    assert second[2]["role"] == "assistant" and second[2]["tool_calls"][0]["id"] == "c0"
    assert second[3]["role"] == "tool" and second[3]["tool_call_id"] == "c0"
    assert json.loads(second[3]["content"])  # the mock API's page
    assert rec["final_text"] == "FINAL ANSWER: 3" and rec["stop_reason"] == "stop"
    assert rec["tokens_in"] == 200 and rec["tokens_out"] == 40 and not rec["truncated"]


def test_provenance_fields_per_turn(spec):
    client, _ = make([completion("FINAL ANSWER: 3", finish="stop")])
    turn = run_episode(client, spec, max_tool_calls=12)["turns"][0]
    assert turn["served_model"] == "openai/gpt-oss-120b" and turn["served_by"] == "Crusoe"
    assert turn["response_id"] == "gen-1" and turn["system_fingerprint"] == "fp_1"
    assert turn["reasoning"] == "check page 1"


def test_cap_forces_final_answer_without_tools(spec):
    client, fake = make([
        completion(calls=[page_call(spec)]),
        completion(calls=[page_call(spec, page=2)]),
        completion("FINAL ANSWER: 3", finish="stop"),
    ])
    rec = run_episode(client, spec, max_tool_calls=1)
    last = fake.calls[-1]
    assert last["tool_choice"] == "none"
    assert last["messages"][-1] == {"role": "user", "content": LIMIT_NOTICE}
    assert rec["hit_cap"] and len(rec["calls"]) == 1 and rec["max_tool_calls"] == 1


@pytest.mark.parametrize("kwargs", [{"finish": "content_filter"}, {"finish": "stop", "refusal": "I can't help."}])
def test_refusals_are_outcomes_not_protocol_failures(spec, kwargs):
    client, _ = make([completion(None, **kwargs)])
    rec = run_episode(client, spec, max_tool_calls=12)
    assert rec["stop_reason"] == "refusal" and rec["empty_reply"] is False


def test_length_is_flagged_as_truncated(spec):
    client, _ = make([completion("FINAL ANSWER: 3 and some", finish="length")])
    rec = run_episode(client, spec, max_tool_calls=12)
    assert rec["truncated"] and rec["stop_reason"] == "length"


def test_unparseable_arguments_reach_the_api_as_an_error(spec):
    client, _ = make([completion(calls=[(spec.target_tool, "{not json")]), completion("FINAL ANSWER: 0", finish="stop")])
    rec = run_episode(client, spec, max_tool_calls=12)
    assert rec["calls"][0]["error"] is not None


def test_provider_error_is_raised_so_the_attempt_is_retried(spec):
    # The SDK parses responses leniently, so OpenRouter's "error" (outside its typed literals) gets through.
    failed = completion("partial text", finish="stop")
    failed.choices[0].finish_reason = "error"
    client, _ = make([failed])
    with pytest.raises(RuntimeError, match="finish_reason=error"):
        run_episode(client, spec, max_tool_calls=12)


def test_empty_glitch_with_no_tokens_is_retried(spec):
    glitch = completion(None, finish="stop")
    glitch.usage.completion_tokens = 0
    client, _ = make([glitch])
    with pytest.raises(RuntimeError, match="0 completion tokens"):
        run_episode(client, spec, max_tool_calls=12)


def test_host_that_rejects_tool_choice_none_falls_back_to_auto(spec):
    class Rejected(Exception):
        status_code = 404

    rejection = Rejected("No endpoints found for openai/gpt-oss-120b. ... Filter by Tool Compatibility removed crusoe/bf16")

    class Fake(FakeCompletions):
        def create(self, **kwargs):
            self.calls.append(copy.deepcopy(kwargs))
            if kwargs["tool_choice"] == "none":
                raise rejection
            return self.script.pop(0)

    client = OpenAICompatibleClient("gpt-test", "model-under-test", api_key_env="NO_SUCH_KEY")
    fake = Fake([completion(calls=[page_call(spec)]), completion(calls=[page_call(spec, page=2)]),
                 completion("FINAL ANSWER: 3", finish="stop")])
    client.client = NS(chat=NS(completions=fake))
    rec = run_episode(client, spec, max_tool_calls=1)
    assert [c["tool_choice"] for c in fake.calls] == ["auto", "auto", "none", "auto"]
    assert rec["hit_cap"] and rec["final_text"] == "FINAL ANSWER: 3"
    assert rec["turns"][-1]["final_tool_choice"] == "auto" and client.final_tool_choice == "auto"


def test_tool_call_in_the_final_turn_is_not_executed(spec):
    client, fake = make([completion(calls=[page_call(spec)]), completion(calls=[page_call(spec, page=2)]),
                         completion("FINAL ANSWER: 3", calls=[page_call(spec, page=3)], finish="tool_calls")])
    rec = run_episode(client, spec, max_tool_calls=1)
    assert len(rec["calls"]) == 1 and rec["final_text"] == "FINAL ANSWER: 3" and len(fake.calls) == 3
