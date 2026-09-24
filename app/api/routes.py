"""The 2 doors. Thin on purpose: calls classify(), route(), get_answer(),
then save_request() - no routing, LLM, or logging logic of its own; those
live in router.py, app/llm/client.py, and app/db/logging.py."""
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.logging import get_request, get_stats, save_request
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
    tools_used: Optional[list[dict[str, Any]]] = None
    gate_log: Optional[list[dict[str, Any]]] = None
    steps: Optional[int] = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/v1/route", response_model=RouteResponse)
def route_message(body: RouteRequest):
    start = time.monotonic()
    request_id = str(uuid.uuid4())
    decision = classify(body.message)
    result = route(decision)
    answer = get_answer(result.route, body.message, decision.complexity_label)
    save_request(request_id, body.message, decision, result, answer, time.monotonic() - start)
    return RouteResponse(
        request_id=request_id,
        decision=decision,
        route=result.route,
        reason=result.reason,
        **answer,
    )


@router.get("/v1/requests/{request_id}")
def get_request_record(request_id: str):
    """(Nice extra) The full logged record for one request - the requests
    row plus its tool_calls, step-ordered. A database problem here is a
    real error response, not fail-open like save_request(): unlike
    logging, nothing else depends on this endpoint succeeding."""
    record = get_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no logged request with id {request_id}")
    return record


@router.get("/v1/stats")
def get_route_stats():
    """(Nice extra) Counts per route, cost/time averages, and how many
    tool calls the gate blocked - computed from real logged data."""
    return get_stats()
