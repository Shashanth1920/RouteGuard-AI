"""File 1: the "form" design. Pydantic catches wrong data automatically -
a bad intent string, or a risk value outside 0-1, fails to build a Decision
at all rather than silently passing through."""
from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["calculation", "coding", "search", "database action", "action", "general", "unknown"]
ComplexityLabel = Literal["simple", "moderate", "complex"]


class Decision(BaseModel):
    intent: Intent
    intent_confidence: float = Field(ge=0, le=1)
    complexity_score: float
    complexity_label: ComplexityLabel
    risk: float = Field(ge=0, le=1)
    needs_tool: float = Field(ge=0, le=1)
    time_taken: float
    is_fallback: bool = False
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    jev_cost: float = 0.0
    """Part 7 Step 3 addition - real per-call cost from the Decisions API's
    own `usage` field, needed to compare Jev's cost against an LLM-only
    decider with real numbers instead of an estimate."""
    """True means Jev didn't actually answer - this is the safe-guess form,
    not a real assessment. "risk=1.0, is_fallback=True" reads as "receptionist
    was absent, treated as an emergency to be safe", never just "emergency"."""
