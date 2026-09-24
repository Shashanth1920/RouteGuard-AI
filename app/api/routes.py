"""The 2 doors. Thin on purpose: calls classify(), route(), then get_answer()
- no routing logic and no LLM call/backup logic of its own; those live in
router.py and app/llm/client.py."""
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.decision.jev_classifier import classify
from app.decision.schemas import Decision
from app.llm.client import get_answer
from app.routing.router import route

router = APIRouter()


class RouteRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class RouteResponse(BaseModel):
    request_id: str
    decision: Decision
    route: str
    reason: str
    answer: Optional[str] = None
    model_used: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost: Optional[float] = None
    llm_time_taken: Optional[float] = None
    error: Optional[str] = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/v1/route", response_model=RouteResponse)
def route_message(body: RouteRequest):
    decision = classify(body.message)
    result = route(decision)
    answer = get_answer(result.route, body.message)
    return RouteResponse(
        request_id=str(uuid.uuid4()),
        decision=decision,
        route=result.route,
        reason=result.reason,
        **answer,
    )
