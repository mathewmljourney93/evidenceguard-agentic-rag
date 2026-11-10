"""M5h (ADR-0026): the real Anthropic adapter composes with the M5g handler factory.

The adapter runs over a scripted, test-owned transport that returns synthetic Messages bodies;
the M5g handler runs over the existing offline review world (fake database, no PostgreSQL).
This is not a production registration and not live-provider evidence: nothing here contacts a
network, and ``run_review`` stays out of the production registry.
"""

import json
from typing import TYPE_CHECKING, Any

import pytest

from evidenceguard_agents.anthropic import AnthropicProvider, AnthropicResponse
from evidenceguard_agents.scripted import FAKE_MODEL_ID
from evidenceguard_domain.jobs import JobStatus
from evidenceguard_domain.review_stages import StageKind, StageShape
from evidenceguard_worker.context import FinishState
from evidenceguard_worker.handlers import production_registry

if TYPE_CHECKING:
    import review_world as rw
else:
    from tests import review_world as rw


class MessagesTransport:
    """Returns one synthetic Messages body per call, in order, echoing the requested model."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls: list[tuple[dict[str, Any], int]] = []

    def post(self, body: bytes, *, timeout_ms: int) -> AnthropicResponse:
        document = json.loads(body)
        self.calls.append((document, timeout_ms))
        reply = {
            "id": f"msg_synthetic_{len(self.calls):02d}",
            "type": "message",
            "role": "assistant",
            "model": document["model"],
            "content": [
                {"type": "thinking", "thinking": "synthetic", "signature": "s"},
                {"type": "text", "text": self.texts.pop(0)},
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        return AnthropicResponse(200, json.dumps(reply).encode("utf-8"))


def test_the_anthropic_adapter_completes_a_review_through_the_m5g_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = rw.World(monkeypatch, template=rw.synthetic_template(1))
    question = world.questions[0].question_id
    transport = MessagesTransport([rw.verifier_json(), rw.analyst_json(question)])
    attempt = world.attempt(world.handler(AnthropicProvider(transport)))

    assert attempt.error is None
    assert world.db.state.job.status is JobStatus.SUCCEEDED
    assert attempt.state.finish is FinishState.COMMITTED
    assert world.db.state.output is not None
    shapes = {(key[1], stage.shape) for key, stage in world.stages().items()}
    assert shapes == {(StageKind.VERIFICATION, StageShape.S1), (StageKind.ANALYSIS, StageShape.S2)}

    # Exactly one transport call per stage, with the canonical body shape and the pinned model.
    assert len(transport.calls) == 2 and transport.texts == []
    for document, timeout_ms in transport.calls:
        assert set(document) == {"max_tokens", "messages", "model", "system"}
        assert document["model"] == FAKE_MODEL_ID
        assert [message["role"] for message in document["messages"]] == ["user"]
        assert type(timeout_ms) is int and 1_000 <= timeout_ms <= 120_000
    verifier, analyst = (document["system"] for document, _ in transport.calls)
    assert verifier != analyst

    # The adapter is constructed here only; nothing registers it.
    assert production_registry().kinds == frozenset({"ingest_revision", "index_revision"})
