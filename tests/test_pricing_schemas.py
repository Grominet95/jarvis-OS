"""Tests unitaires des helpers purs de kernel.schemas (pricing + validation)."""

from __future__ import annotations

import pytest

from jarvis.kernel.schemas import (
    Initiative,
    Step,
    calculate_cost,
    needs_human_validation,
    validate_step,
)
from jarvis.kernel.vocab import AutonomyLevel


def test_calculate_cost_anthropic_tokens() -> None:
    cost = calculate_cost(
        "anthropic", "claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert cost == pytest.approx(18.0)


def test_calculate_cost_openai_with_images() -> None:
    cost = calculate_cost("openai", "gpt-4o", input_tokens=0, output_tokens=0, images=10)
    assert cost == pytest.approx(0.02)


def test_calculate_cost_elevenlabs_chars() -> None:
    cost = calculate_cost("elevenlabs", "eleven_turbo_v2_5", characters=1000)
    assert cost == pytest.approx(0.18)


def test_calculate_cost_deepgram_minutes() -> None:
    cost = calculate_cost("deepgram", "nova-2", audio_minutes=10)
    assert cost == pytest.approx(0.059)


def test_calculate_cost_unknown_provider_is_zero() -> None:
    assert calculate_cost("nope", "model", input_tokens=1000) == 0.0


def test_calculate_cost_unknown_model_is_zero() -> None:
    assert calculate_cost("anthropic", "totally-unknown-model-xyz", input_tokens=1000) == 0.0


def test_calculate_cost_prefix_match() -> None:
    cost = calculate_cost(
        "anthropic", "claude-haiku-4-5-20251001", input_tokens=1_000_000
    )
    assert cost == pytest.approx(0.25)


def test_calculate_cost_no_kwargs_is_zero() -> None:
    assert calculate_cost("anthropic", "claude-sonnet-4-6") == 0.0


def test_validate_step_ok() -> None:
    step = Step(id="s1", title="t", description="d", success_criterion="le fichier existe")
    validate_step(step)


def test_validate_step_rejects_empty_criterion() -> None:
    step = Step(id="s1", title="t", description="d", success_criterion="   ")
    with pytest.raises(ValueError, match="success_criterion"):
        validate_step(step)


def _initiative(level: AutonomyLevel, requires: bool = False) -> Initiative:
    from jarvis.kernel.schemas import ExecutionMode, InitiativeType, Priority

    return Initiative(
        id="i1",
        type=InitiativeType.SUGGESTION,
        title="t",
        context="c",
        reasoning="r",
        action="a",
        priority=Priority.LOW,
        execution_mode=ExecutionMode.NOTIFY,
        autonomy_level=level,
        requires_validation=requires,
    )


def test_needs_human_validation_external_always_true() -> None:
    init = _initiative(AutonomyLevel.EXTERNAL_ACTION, requires=False)
    assert needs_human_validation(init) is True


def test_needs_human_validation_respects_flag() -> None:
    init = _initiative(AutonomyLevel.SUGGEST, requires=True)
    assert needs_human_validation(init) is True


def test_needs_human_validation_default_false() -> None:
    init = _initiative(AutonomyLevel.SUGGEST, requires=False)
    assert needs_human_validation(init) is False
