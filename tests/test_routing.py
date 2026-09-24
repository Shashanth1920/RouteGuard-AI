"""All Decision forms here are hand-made - zero API calls, zero network."""
from app.config import INTENT_CONFIDENCE_CUTOFF, NEEDS_TOOL_CUTOFF, RISK_CUTOFF
from app.decision.schemas import Decision
from app.routing.router import route


def make_decision(**overrides) -> Decision:
    defaults = dict(
        intent="general",
        intent_confidence=1.0,
        complexity_score=0.0,
        complexity_label="simple",
        risk=0.0,
        needs_tool=0.0,
        time_taken=0.1,
        is_fallback=False,
    )
    defaults.update(overrides)
    return Decision(**defaults)


# --- one test per rule -------------------------------------------------------

def test_rule1_fallback_goes_to_human_review():
    d = make_decision(is_fallback=True, intent="unknown", risk=1.0)
    result = route(d)
    assert result.route == "human_review"
    assert result.rule == 1


def test_rule2_high_risk_goes_to_human_review():
    d = make_decision(risk=0.95)
    result = route(d)
    assert result.route == "human_review"
    assert result.rule == 2


def test_rule3_low_confidence_goes_to_strong_llm():
    d = make_decision(intent_confidence=0.4)
    result = route(d)
    assert result.route == "strong_llm"
    assert result.rule == 3


def test_rule4_complex_goes_to_strong_llm():
    d = make_decision(complexity_label="complex", complexity_score=1.9)
    result = route(d)
    assert result.route == "strong_llm"
    assert result.rule == 4


def test_rule5_needs_tool_goes_to_agent():
    d = make_decision(needs_tool=0.9)
    result = route(d)
    assert result.route == "agent"
    assert result.rule == 5


def test_rule6_default_goes_to_small_llm():
    d = make_decision()  # low risk, confident, simple, no tool
    result = route(d)
    assert result.route == "small_llm"
    assert result.rule == 6


# --- rule order: safety beats everything, including "looks simple" ---------

def test_risky_and_simple_goes_to_human_review_not_small_llm():
    # "Delete all users": simple to execute, but risky. If the "simple"
    # rule (6) ran before the risk rule (2), this would wrongly go cheap.
    d = make_decision(complexity_label="simple", risk=0.95, needs_tool=0.6)
    result = route(d)
    assert result.route == "human_review"
    assert result.rule == 2


# --- edge cases at the risk cutoff -------------------------------------------

def test_risk_exactly_at_cutoff_triggers_human_review():
    d = make_decision(risk=RISK_CUTOFF)
    result = route(d)
    assert result.route == "human_review"
    assert result.rule == 2


def test_risk_just_below_cutoff_does_not_trigger_human_review():
    d = make_decision(risk=RISK_CUTOFF - 0.01)
    result = route(d)
    assert result.route != "human_review"
    assert result.rule != 2


# --- every result includes a reason -----------------------------------------

def test_every_route_includes_a_nonempty_reason():
    cases = [
        make_decision(is_fallback=True),
        make_decision(risk=0.9),
        make_decision(intent_confidence=0.3),
        make_decision(complexity_label="complex"),
        make_decision(needs_tool=0.8),
        make_decision(),
    ]
    for d in cases:
        result = route(d)
        assert result.reason and len(result.reason) > 0
