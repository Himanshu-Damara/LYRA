"""Persistent source-checklist, task filtering, and review-packet API."""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import asc

router = APIRouter(prefix="/api/task-review", tags=["task-review"])
VALID_STATUSES = {"Draft", "In review", "Ready"}
VALID_SECTION_STATUSES = {"complete", "review", "missing"}


class SectionUpdate(BaseModel):
    status: Optional[str] = None
    source: Optional[str] = Field(default=None, max_length=2000)
    generated_content: Optional[str] = Field(default=None, max_length=100000)
    notes: Optional[str] = Field(default=None, max_length=10000)


class TaskUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=10000)
    status: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _warnings(task) -> list[str]:
    try:
        value = json.loads(task.validation_warnings or "[]")
        return [str(item) for item in value] if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _task_dict(task, sections) -> dict:
    ordered = sorted(sections, key=lambda section: (section.position, section.id))
    required = [section for section in ordered if section.required]
    required_completed = sum(section.status == "complete" and bool((section.source or "").strip()) for section in required)
    missing_required = [section.name for section in required if section.status != "complete" or not (section.source or "").strip()]
    generated_count = sum(bool((section.generated_content or "").strip()) for section in ordered)
    warnings = _warnings(task)
    ready = not missing_required
    return {
        "id": task.id, "title": task.title, "summary": task.summary or "", "owner": task.owner, "agent": task.agent,
        "status": task.status, "notes": task.notes or "", "validation_warnings": warnings,
        "created_at": task.created_at, "updated_at": task.updated_at,
        "sections": [{"id": s.id, "name": s.name, "required": bool(s.required), "source": s.source or "", "status": s.status,
                      "generated_content": s.generated_content or "", "notes": s.notes or ""} for s in ordered],
        "completion": {
            "complete": required_completed,
            "total": len(required),
            "percent": round((required_completed / len(required)) * 100) if required else 0,
            "required_total": len(required),
            "required_completed": required_completed,
            "required_missing": len(missing_required),
        },
        "generated_section_count": generated_count,
        "warning_count": len(warnings),
        "missing_field_count": len(missing_required),
        "missing_required": missing_required, "ready": ready,
    }


def _load_task(db, task_id: str):
    from gitd.models.task_review import ReviewSection, ReviewTask

    task = db.get(ReviewTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="agent task not found")
    sections = db.query(ReviewSection).filter(ReviewSection.task_id == task.id).order_by(asc(ReviewSection.position)).all()
    return task, sections


def _sync_readiness_status(task, sections) -> None:
    """Prevent a persisted READY status from disagreeing with checklist data."""
    readiness = _task_dict(task, sections)
    if readiness["ready"]:
        task.status = "Ready"
    elif task.status == "Ready":
        task.status = "In review"


@router.get("/tasks", summary="List Agent Review Tasks")
def list_review_tasks(search: str = Query("", max_length=200), section: Optional[str] = Query(None, max_length=200),
                      status: Optional[str] = Query(None, max_length=50), owner: Optional[str] = Query(None, max_length=200),
                      agent: Optional[str] = Query(None, max_length=200), missing_data: Optional[bool] = Query(None)):
    from gitd.models.base import SessionLocal
    from gitd.models.task_review import ReviewSection, ReviewTask

    db = SessionLocal()
    try:
        tasks = db.query(ReviewTask).order_by(ReviewTask.updated_at.desc()).all()
        term, rows, section_values, owner_values, agent_values = search.strip().lower(), [], set(), set(), set()
        for task in tasks:
            sections = db.query(ReviewSection).filter(ReviewSection.task_id == task.id).all()
            section_values.update(s.name for s in sections)
            owner_values.add(task.owner)
            agent_values.add(task.agent)
            item = _task_dict(task, sections)
            searchable = " ".join([task.id, task.title, task.summary or "", task.owner, task.agent] +
                                  [v for s in item["sections"] for v in (s["name"], s["source"], s["generated_content"], s["notes"])]).lower()
            if term and term not in searchable: continue
            if section and not any(s["name"] == section for s in item["sections"]): continue
            if status and task.status != status: continue
            if owner and task.owner != owner: continue
            if agent and task.agent != agent: continue
            has_missing = bool(item["missing_required"])
            if missing_data is True and not has_missing: continue
            if missing_data is False and has_missing: continue
            rows.append(item)
        return {"data": rows, "total": len(rows), "filters": {"sections": sorted(section_values), "statuses": sorted(VALID_STATUSES), "owners": sorted(owner_values), "agents": sorted(agent_values)}}
    finally:
        db.close()


@router.get("/tasks/{task_id}", summary="Get Agent Review Task")
def get_review_task(task_id: str):
    from gitd.models.base import SessionLocal
    db = SessionLocal()
    try:
        task, sections = _load_task(db, task_id)
        return _task_dict(task, sections)
    finally:
        db.close()


@router.patch("/tasks/{task_id}", summary="Update Agent Review Task")
def update_review_task(task_id: str, update: TaskUpdate):
    from gitd.models.base import SessionLocal
    if update.status is not None and update.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    db = SessionLocal()
    try:
        task, sections = _load_task(db, task_id)
        if update.status == "Ready" and not _task_dict(task, sections)["ready"]:
            raise HTTPException(status_code=422, detail="A task cannot be marked Ready while required checklist items are missing")
        if update.notes is not None: task.notes = update.notes
        if update.status is not None: task.status = update.status
        task.updated_at = _now()
        db.commit(); db.refresh(task)
        return _task_dict(task, sections)
    finally:
        db.close()


@router.patch("/tasks/{task_id}/sections/{section_id}", summary="Update Source Checklist Item")
def update_review_section(task_id: str, section_id: str, update: SectionUpdate):
    from gitd.models.base import SessionLocal
    from gitd.models.task_review import ReviewSection
    if update.status is not None and update.status not in VALID_SECTION_STATUSES:
        raise HTTPException(status_code=422, detail="section status must be complete, review, or missing")
    db = SessionLocal()
    try:
        task, sections = _load_task(db, task_id)
        section = db.query(ReviewSection).filter_by(id=section_id, task_id=task_id).first()
        if not section: raise HTTPException(status_code=404, detail="checklist item not found")
        for field in ("status", "source", "generated_content", "notes"):
            value = getattr(update, field)
            if value is not None: setattr(section, field, value)
        _sync_readiness_status(task, sections)
        section.updated_at = _now(); task.updated_at = section.updated_at
        db.commit(); db.refresh(task)
        return _task_dict(task, sections)
    finally:
        db.close()


def _packet(task, sections) -> str:
    data = _task_dict(task, sections)
    lines = ["# Agent Task Review Packet", "", "## Agent Task", "", f"- **ID:** {data['id']}", f"- **Title:** {data['title']}",
             f"- **Owner:** {data['owner']}", f"- **Agent:** {data['agent']}", f"- **Status:** {data['status']}",
             f"- **Checklist:** {data['completion']['complete']}/{data['completion']['total']} required complete ({data['completion']['percent']}%)",
             f"- **Readiness:** {'READY' if data['ready'] else 'MISSING REQUIRED INPUTS'}", "", "## 1. Generated Sections", ""]
    for s in data["sections"]:
        lines += [f"### {s['name']}", "", f"**Status:** {s['status']}", f"**Source:** {s['source'] or 'MISSING'}", "", s["generated_content"] or "No generated content.", ""]
    lines += ["## 2. Source Checklist", ""]
    for s in data["sections"]:
        mark = "x" if s["status"] == "complete" and s["source"] else " "
        lines.append(f"- [{mark}] {s['name']} ({'required' if s['required'] else 'optional'}) — {s['status']}; source: {s['source'] or 'MISSING'}")
    lines += ["", "## 3. Validation Warnings", ""] + ([f"- {w}" for w in data["validation_warnings"]] or ["No validation warnings."])
    lines += ["", "## 4. Missing Required Data / Fields", ""] + ([f"- {m}" for m in data["missing_required"]] or ["No required inputs are missing."])
    lines += ["", "## 5. User Notes", "", data["notes"] or "No user notes.", "", "## 6. Review Status", "", data["status"], "", "## 7. Summary", "", f"- Required checklist: {data['completion']['complete']}/{data['completion']['total']} ({data['completion']['percent']}%)", f"- Generated sections: {data['generated_section_count']}", f"- Validation warnings: {data['warning_count']}", f"- Missing required fields: {data['missing_field_count']}", ""]
    return "\n".join(lines)


@router.get("/tasks/{task_id}/packet", summary="Download Review Packet")
def download_review_packet(task_id: str):
    from gitd.models.base import SessionLocal
    db = SessionLocal()
    try:
        task, sections = _load_task(db, task_id)
        return PlainTextResponse(_packet(task, sections), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="review-packet-{task.id}.md"'})
    finally:
        db.close()


def seed_review_tasks() -> None:
    """Seed meaningful demo records once; never overwrite user edits."""
    import json
    from gitd.models.base import SessionLocal
    from gitd.models.task_review import ReviewSection, ReviewTask

    now = _now()
    seeds = [
        ("task-whatsapp-001", "Send a WhatsApp message", "Open WhatsApp, find Vansh Cu, and send a short greeting.", "Product QA", "Ghost Android Agent", "Ready", "Judge-ready completed sample.", [], [
            ("goal", "Goal & scope", "User brief", "complete", "Send hello to the Vansh Cu WhatsApp contact.", "Scope is limited to one message."),
            ("inputs", "Inputs & sources", "Phone + WhatsApp contact", "complete", "Device and contact were verified.", "Phone connected over ADB."),
            ("steps", "Generated steps", "WhatsApp skill", "complete", "Open WhatsApp, search Vansh Cu, type, and send.", "Workflow completed."),
            ("validation", "Validation & review", "Run log + UI state", "complete", "Send action was verified.", "Ready for review."),
        ]),
        ("task-instagram-002", "Like the first Instagram post", "Open Instagram and like the first visible feed post.", "Growth Ops", "Ghost Android Agent", "In review", "Need device and account context before review.", ["Post-like result has not been verified."], [
            ("goal", "Goal & scope", "User brief", "complete", "Like the first visible feed post.", ""), ("inputs", "Inputs & sources", "", "missing", "", "Device and account context are missing."),
            ("steps", "Generated steps", "Instagram skill draft", "review", "Open Instagram and locate the first post.", "Like control needs verification."), ("validation", "Validation & review", "", "missing", "", "No postcondition captured."),
        ]),
        ("task-settings-003", "Enable dark mode in Settings", "Navigate to Android display settings and enable dark theme.", "Mobile QA", "Settings Explorer", "Draft", "OS version is not recorded.", ["No postcondition captured."], [
            ("goal", "Goal & scope", "Test case", "complete", "Enable the system dark theme.", ""), ("inputs", "Inputs & sources", "Android Settings", "review", "Android device required.", "OS version is not recorded."),
            ("steps", "Generated steps", "Settings Explorer", "review", "Open Settings → Display → Dark theme.", "Confirm label by Android version."), ("validation", "Validation & review", "", "missing", "", "No postcondition captured."),
        ]),
    ]
    db = SessionLocal()
    try:
        for tid, title, summary, owner, agent, status, notes, warnings, sections in seeds:
            if db.get(ReviewTask, tid): continue
            db.add(ReviewTask(id=tid, title=title, summary=summary, owner=owner, agent=agent, status=status, notes=notes, validation_warnings=json.dumps(warnings), created_at=now, updated_at=now))
            # No ORM relationship is needed for this small bounded feature,
            # so flush each parent before inserting its FK-backed sections.
            db.flush()
            for pos, (sid, name, source, section_status, content, section_notes) in enumerate(sections):
                db.add(ReviewSection(id=f"{tid}-{sid}", task_id=tid, name=name, required=True, source=source, status=section_status, generated_content=content, notes=section_notes, position=pos, created_at=now, updated_at=now))
        db.commit()
    finally:
        db.close()
