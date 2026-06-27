"""Customer-authored capability templates (Phase 3). Tenant-scoped CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.tenant import current_org
from apps.api.models.db import get_session
from apps.api.services.templates import (
    create_template,
    delete_template,
    draft_template,
    list_templates,
)

router = APIRouter()


class TemplateBody(BaseModel):
    topic: str
    title: str
    description: str = ""
    inputs: list[str] = []
    tools: list[dict] = []
    intents: list[str] = []
    keywords: list[str] = []
    slug: str | None = None


@router.get("/templates")
def templates_list(db: Session = Depends(get_session)):
    """All capability templates this tenant can compile — built-in + its own."""
    return list_templates(db, current_org())


class DraftBody(BaseModel):
    description: str


@router.post("/templates/draft")
def templates_draft(body: DraftBody):
    """Draft a capability template from a plain-English workflow description (no save).
    Uses the real model when configured; a deterministic heuristic otherwise."""
    res = draft_template(body.description)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/templates")
def templates_create(body: TemplateBody, db: Session = Depends(get_session)):
    res = create_template(db, current_org(), topic=body.topic, title=body.title,
                          description=body.description, inputs=body.inputs, tools=body.tools,
                          intents=body.intents, keywords=body.keywords, slug=body.slug)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.delete("/templates/{topic}")
def templates_delete(topic: str, db: Session = Depends(get_session)):
    res = delete_template(db, current_org(), topic)
    if res.get("error"):
        raise HTTPException(status_code=404, detail="custom template not found in this tenant")
    return res
