"""M7 (ADR-0029): an evaluated review pins exactly the configuration the review API would."""

import pytest

from evidenceguard_api.reviews import _pinned_configuration
from evidenceguard_evaluation.contract import CONTRACT_MODEL_ID
from evidenceguard_worker.evaluation_run import TEMPLATE, review_configuration


@pytest.mark.parametrize("model", [CONTRACT_MODEL_ID, "claude-example-20260101"])
def test_the_eval_configuration_digest_equals_the_api_pinned_configuration(model: str) -> None:
    ours = review_configuration(model)
    theirs = _pinned_configuration(*TEMPLATE, model)
    assert ours.configuration_sha256 == theirs.configuration_sha256
    assert ours.canonical_bytes() == theirs.canonical_bytes()
    assert ours.model_id == model
