from fastapi import APIRouter, Depends, HTTPException
from app.modules.practice.models import PracticeConfig, PracticeSubmit
from app.modules.practice.service import PracticeService
from app.modules.auth.dependencies import get_current_user

router = APIRouter()


@router.post("/start")
async def start_practice(
    config: PracticeConfig,
    user: dict = Depends(get_current_user)
):
    """开始（或恢复）练习：相同配置存在未完成会话时从下一未完成题继续。"""
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
        return PracticeService.build_session_payload(session, question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/submit")
async def submit_answer(
    submit_data: PracticeSubmit,
    user: dict = Depends(get_current_user)
):
    """提交当前题答案：每题只接受一次，重复提交回读既有结果。"""
    try:
        return await PracticeService.submit_answer(
            session_id=submit_data.session_id,
            user_id=str(user["_id"]),
            question_id=submit_data.question_id,
            user_answer=submit_data.user_answer
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """按会话恢复练习现场（刷新/重进后回读）。"""
    session = await PracticeService.get_session(session_id, str(user["_id"]))
    if not session:
        raise HTTPException(status_code=404, detail="练习会话不存在")

    question = await PracticeService.get_current_question(session)
    return PracticeService.build_session_payload(session, question)


@router.get("/session/{session_id}/question/{index}")
async def get_question_at(
    session_id: str,
    index: int,
    user: dict = Depends(get_current_user)
):
    """只读查看指定位置的题目及作答记录，不影响练习进度。"""
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
