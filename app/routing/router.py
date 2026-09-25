"""File: app/routing/router.py - the hospital rulebook.

Reads the form the receptionist (jev_classifier) already filled in and
decides where the request goes. Pure Python: no API calls, no AI. First
matching rule wins, and safety rules run before cost rules - "delete all
users" is simple and cheap-looking, but it's also risky, so the risk
check must fire before anything asks "is this simple enough for the
cheap model?"
"""
from typing import Literal

from pydantic import BaseModel

from app.config import INTENT_CONFIDENCE_CUTOFF, NEEDS_TOOL_CUTOFF, RISK_CUTOFF
from app.decision.schemas import Decision

Route = Literal["human_review", "strong_llm", "agent", "small_llm"]


class RouteResult(BaseModel):
    route: Route
    reason: str
    rule: int  # which of the 6 rules fired, 1-6


def route(decision: Decision) -> RouteResult:
    if decision.is_fallback:
        return RouteResult(
            route="human_review",
            reason="Jev failed (is_fallback=True) - can't assess, treated as an emergency",
            rule=1,
        )

    if decision.risk >= RISK_CUTOFF:
        return RouteResult(
            route="human_review",
            reason=f"risk {decision.risk:.2f} >= cutoff {RISK_CUTOFF}",
            rule=2,
        )

    # A clear tool need skips this rule: Jev often wavers between tool intents
    # (database action vs. search) while needs_tool is ~0.95, and strong_llm has
    # no tools. Risk (rule 2) and the Safety Gate still guard the agent path.
    if decision.intent_confidence < INTENT_CONFIDENCE_CUTOFF and decision.needs_tool < NEEDS_TOOL_CUTOFF:
        return RouteResult(
            route="strong_llm",
            reason=f"intent confidence {decision.intent_confidence:.2f} < cutoff {INTENT_CONFIDENCE_CUTOFF} - Jev is unsure",
            rule=3,
        )

    if decision.complexity_label == "complex":
        return RouteResult(
            route="strong_llm",
            reason=f"complexity is 'complex' (score {decision.complexity_score:.2f})",
            rule=4,
        )

    if decision.needs_tool >= NEEDS_TOOL_CUTOFF:
        return RouteResult(
            route="agent",
            reason=f"needs_tool {decision.needs_tool:.2f} >= cutoff {NEEDS_TOOL_CUTOFF}",
            rule=5,
        )

    return RouteResult(
        route="small_llm",
        reason="low risk, confident, not complex, no tool needed",
        rule=6,
    )
