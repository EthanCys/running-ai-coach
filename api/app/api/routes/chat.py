"""Chat endpoint — natural-language entry to the AI running coach.

POST /api/v1/chat
  body: { "message": "分析我最近一次跑步" }
  header: X-Coros-Session (optional; resolves to a COROS access token)
  → { reply, intent, report_card?, records?, presets }

The heavy lifting (intent → MCP orchestration → analysis) lives in
services/chat_orchestrator.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services import chat_orchestrator
from app.api.routes.auth import get_session_token


router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    intent: str
    report_card: dict | None = None
    records: list[dict] | None = None
    presets: list[dict]


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, x_coros_session: str | None = Header(default=None)) -> ChatResponse:
    access_token = get_session_token(x_coros_session)
    result = await chat_orchestrator.handle_chat(req.message, access_token)
    return ChatResponse(
        reply=result["reply"],
        intent=result["intent"],
        report_card=result.get("report_card"),
        records=result.get("records"),
        presets=chat_orchestrator.PRESETS,
    )


@router.get("/presets")
def presets() -> dict:
    return {"presets": chat_orchestrator.PRESETS}
