from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.modules.practice.models import PracticeConfig, PracticeSubmit
from app.modules.practice.service import PracticeService
from app.modules.auth.dependencies import get_current_user

router = APIRouter()


def _session_payload(session: dict) -> dict:
    return {
        "session_id": session["id"],
        "mode": session["mode"],
        "subject_id": session["subject_id"],
        "knowledge_ids": session.get("knowledge_ids"),
        "status": session.get("status", "in_progress"),
        "progress": PracticeService._build_progress(session)
    }


@router.post("/start")
async def start_practice(
    config: PracticeConfig,
    user: dict = Depends(get_current_user)
):
    try:
        session = await PracticeService.create_session(
            user_id=str(user["_id"]),
            mode=config.mode,
            subject_id=config.subject_id,
            knowledge_ids=config.knowledge_ids,
            question_count=config.question_count,
            difficulty=config.difficulty
        )

        question = await PracticeService.get_current_question(session)
        return {
            **_session_payload(session),
            "current_question": PracticeService._question_response(question)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/active")
async def get_active_session(
    mode: str = Query(...),
    subject_id: str = Query(...),
    knowledge_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """查找该知识点下未完成的练习会话，用于退出后续练。"""
    knowledge_ids = [knowledge_id] if knowledge_id else None
    session = await PracticeService.get_active_session(
        user_id=str(user["_id"]),
        mode=mode,
        subject_id=subject_id,
        knowledge_ids=knowledge_ids
    )
    if not session:
        return None
    return _session_payload(session)


@router.post("/submit")
async def submit_answer(
    submit_data: PracticeSubmit,
    user: dict = Depends(get_current_user)
):
    try:
        result = await PracticeService.submit_answer(
            session_id=submit_data.session_id,
            user_id=str(user["_id"]),
            question_id=submit_data.question_id,
            user_answer=submit_data.user_answer
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/question/{session_id}/{index}")
async def get_question_at(
    session_id: str,
    index: int,
    user: dict = Depends(get_current_user)
):
    """只读获取指定位置的题目与作答记录，不改进度。"""
    try:
        return await PracticeService.get_question_at(
            session_id=session_id,
            user_id=str(user["_id"]),
            index=index
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/progress/{session_id}")
async def get_progress(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        return await PracticeService.get_session_progress(
            session_id=session_id,
            user_id=str(user["_id"])
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    session = await PracticeService.get_session(session_id, str(user["_id"]))
    if not session:
        raise HTTPException(status_code=404, detail="练习会话不存在")

    question = await PracticeService.get_current_question(session)
    return {
        **_session_payload(session),
        "current_question": PracticeService._question_response(question)
    }
