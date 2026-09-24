"""The 2 doors. Thin on purpose: calls classify() and route(), no routing
logic of its own - if a rule needs to change, it changes in router.py, not here."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.decision.jev_classifier import classify
from app.decision.schemas import Decision
from app.routing.router import route

router = APIRouter()


class RouteRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class RouteResponse(BaseModel):
    request_id: str
    decision: Decision
    route: str
    reason: str


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/v1/route", response_model=RouteResponse)
def route_message(body: RouteRequest):
    decision = classify(body.message)
    result = route(decision)
    return RouteResponse(
        request_id=str(uuid.uuid4()),
        decision=decision,
        route=result.route,
        reason=result.reason,
    )
