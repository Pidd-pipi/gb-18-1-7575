from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
from app.core.database import get_db
from app.core.redis import get_redis, cache_dumps, cache_loads
from app.modules.questions.service import QuestionService

CACHE_TTL = 3600 * 24


class PracticeService:
    @staticmethod
    def _cache_key(user_id: str, session_id: str) -> str:
        return f"practice:{user_id}:{session_id}"

    @staticmethod
    async def _cache_session(session: dict):
        redis = get_redis()
        if not redis:
            return
        key = PracticeService._cache_key(session["user_id"], session["id"])
        await redis.setex(key, CACHE_TTL, cache_dumps(session))

    @staticmethod
    def _normalize_session(session: dict) -> dict:
        session["id"] = str(session["_id"])
        session["_id"] = str(session["_id"])
        session.setdefault("status", "in_progress")
        session.setdefault("answers", {})
        session.setdefault("correct_count", 0)
        session.setdefault("current_index", 0)
        return session

    @staticmethod
    def _question_response(question: Optional[dict]) -> Optional[dict]:
        if not question:
            return None
        return {
            "id": str(question["_id"]),
            "type": question["type"],
            "content": question["content"],
            "options": question.get("options"),
            "difficulty": question["difficulty"],
            "knowledge_ids": question.get("knowledge_ids", [])
        }

    @staticmethod
    def _build_progress(session: dict) -> dict:
        answers = session.get("answers", {})
        answered = len(answers)
        correct = sum(1 for a in answers.values() if a.get("is_correct"))
        total = session.get("total", len(session.get("question_ids", [])))
        return {
            "current": min(session.get("current_index", 0), total),
            "total": total,
            "answered": answered,
            "correct": correct,
            "accuracy": round(correct / answered * 100, 1) if answered else 0,
            "status": session.get("status", "in_progress")
        }

    @staticmethod
    async def create_session(
        user_id: str,
        mode: str,
        subject_id: str,
        knowledge_ids: Optional[List[str]] = None,
        question_count: int = 20,
        difficulty: Optional[str] = None,
        question_ids: Optional[List[str]] = None
    ) -> dict:
        db = get_db()

        if question_ids:
            # 显式指定题目（如错题重练），保持给定顺序
            questions = await QuestionService.get_questions_by_ids(question_ids)
        elif mode == "random":
            questions = await QuestionService.get_random_questions(
                subject_id=subject_id,
                knowledge_ids=knowledge_ids,
                difficulty=difficulty,
                count=question_count
            )
        else:
            query = {"subject_id": subject_id}
            if knowledge_ids:
                query["knowledge_ids"] = {"$in": knowledge_ids}
            if difficulty:
                query["difficulty"] = difficulty
            # 固定题序：按入库时间与主键排序，保证同一知识点每次练习顺序一致
            cursor = db.questions.find(query).sort(
                [("created_at", 1), ("_id", 1)]
            ).limit(question_count)
            questions = await cursor.to_list(length=question_count)

        if not questions:
            raise ValueError("没有找到符合条件的题目")

        question_ids = [str(q["_id"]) for q in questions]
        now = datetime.utcnow()
        session_dict = {
            "user_id": user_id,
            "mode": mode,
            "subject_id": subject_id,
            "knowledge_ids": knowledge_ids,
            "question_ids": question_ids,
            "current_index": 0,
            "answers": {},
            "total": len(question_ids),
            "correct_count": 0,
            "status": "in_progress",
            "created_at": now,
            "updated_at": now,
            "finished_at": None
        }

        result = await db.practice_sessions.insert_one(session_dict)
        session_dict["_id"] = str(result.inserted_id)
        session_dict["id"] = str(result.inserted_id)

        await PracticeService._cache_session(session_dict)
        return session_dict

    @staticmethod
    async def get_session(session_id: str, user_id: str) -> Optional[dict]:
        db = get_db()
        redis = get_redis()

        if redis:
            cached = await redis.get(PracticeService._cache_key(user_id, session_id))
            if cached:
                return cache_loads(cached)

        if not ObjectId.is_valid(session_id):
            return None
        session = await db.practice_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id
        })

        if session:
            session = PracticeService._normalize_session(session)
            await PracticeService._cache_session(session)

        return session

    @staticmethod
    async def get_active_session(
        user_id: str,
        mode: str,
        subject_id: str,
        knowledge_ids: Optional[List[str]] = None
    ) -> Optional[dict]:
        """查找用户在该范围内最近一次未完成的练习，用于退出后恢复。"""
        db = get_db()
        query = {
            "user_id": user_id,
            "mode": mode,
            "subject_id": subject_id,
            "status": "in_progress"
        }
        if knowledge_ids:
            query["knowledge_ids"] = knowledge_ids
        else:
            query["knowledge_ids"] = None

        session = await db.practice_sessions.find_one(
            query, sort=[("updated_at", -1)]
        )
        if session:
            session = PracticeService._normalize_session(session)
            await PracticeService._cache_session(session)
        return session

    @staticmethod
    async def get_current_question(session: dict) -> Optional[dict]:
        current_index = session.get("current_index", 0)
        question_ids = session.get("question_ids", [])
        if 0 <= current_index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[current_index])
        return None

    @staticmethod
    async def get_question_at(
        session_id: str,
        user_id: str,
        index: int
    ) -> Dict[str, Any]:
        """按位置只读获取题目与已保存的作答记录，不改变练习进度。"""
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        question_ids = session.get("question_ids", [])
        if index < 0 or index >= len(question_ids):
            raise ValueError("题目位置超出范围")

        question_id = question_ids[index]
        question = await QuestionService.get_question_by_id(question_id)
        if not question:
            raise ValueError("题目不存在")

        record = session.get("answers", {}).get(question_id)
        return {
            "index": index,
            "total": len(question_ids),
            "question": PracticeService._question_response(question),
            "record": record
        }

    @staticmethod
    async def submit_answer(
        session_id: str,
        user_id: str,
        question_id: str,
        user_answer: Any
    ) -> Dict[str, Any]:
        db = get_db()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        question_ids = session.get("question_ids", [])
        answers = session.get("answers", {})

        # 幂等：已作答的题目直接返回已保存的结果，绝不覆盖既有记录
        if question_id in answers:
            return PracticeService._submit_response(session, question_id, answers[question_id])

        if session.get("status") == "finished":
            raise ValueError("本次练习已完成，无法继续提交")

        current_index = session.get("current_index", 0)
        if current_index >= len(question_ids):
            raise ValueError("本次练习已完成")

        # 防跳题：只能作答当前位置的题目
        if question_id != question_ids[current_index]:
            raise ValueError("请按顺序作答当前题目")

        result = await QuestionService.check_answer(question_id, user_answer, user_id)

        record = {
            "user_answer": user_answer,
            "is_correct": result.is_correct,
            "correct_answer": result.correct_answer,
            "explanation": result.explanation,
            "submitted_at": datetime.utcnow().isoformat()
        }

        new_index = current_index + 1
        is_finished = new_index >= len(question_ids)
        new_correct_count = session.get("correct_count", 0) + (1 if result.is_correct else 0)
        now = datetime.utcnow()

        # 正确答案、解析、得分与下一题位置在同一次写入中保存；
        # 过滤条件确保同一题只接受首次提交，并发重复提交不会覆盖
        update_set = {
            f"answers.{question_id}": record,
            "correct_count": new_correct_count,
            "current_index": new_index,
            "status": "finished" if is_finished else "in_progress",
            "updated_at": now
        }
        if is_finished:
            update_set["finished_at"] = now

        update_result = await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id), f"answers.{question_id}": {"$exists": False}},
            {"$set": update_set}
        )

        if update_result.modified_count == 0:
            # 并发重复提交：回读已保存的结果返回，不覆盖
            fresh = await db.practice_sessions.find_one({
                "_id": ObjectId(session_id),
                "user_id": user_id
            })
            if fresh:
                fresh = PracticeService._normalize_session(fresh)
                await PracticeService._cache_session(fresh)
                saved = fresh.get("answers", {}).get(question_id)
                if saved:
                    return PracticeService._submit_response(fresh, question_id, saved)
            raise ValueError("提交冲突，请重试")

        if not result.is_correct:
            await PracticeService._add_to_errors(user_id, question_id)

        answers[question_id] = record
        session["answers"] = answers
        session["correct_count"] = new_correct_count
        session["current_index"] = new_index
        session["status"] = "finished" if is_finished else "in_progress"
        await PracticeService._cache_session(session)

        return PracticeService._submit_response(session, question_id, record)

    @staticmethod
    def _submit_response(session: dict, question_id: str, record: dict) -> Dict[str, Any]:
        progress = PracticeService._build_progress(session)
        return {
            "question_id": question_id,
            "is_correct": record.get("is_correct"),
            "user_answer": record.get("user_answer"),
            "correct_answer": record.get("correct_answer"),
            "explanation": record.get("explanation"),
            "submitted_at": record.get("submitted_at"),
            "progress": progress,
            "is_finished": session.get("status") == "finished"
        }

    @staticmethod
    async def _add_to_errors(user_id: str, question_id: str):
        db = get_db()
        question = await QuestionService.get_question_by_id(question_id)
        if not question:
            return

        existing = await db.errors.find_one({
            "user_id": user_id,
            "question_id": question_id
        })

        if existing:
            await db.errors.update_one(
                {"_id": existing["_id"]},
                {
                    "$inc": {"wrong_count": 1},
                    "$set": {"last_wrong_at": datetime.utcnow()}
                }
            )
        else:
            await db.errors.insert_one({
                "user_id": user_id,
                "question_id": question_id,
                "subject_id": question.get("subject_id"),
                "knowledge_ids": question.get("knowledge_ids", []),
                "wrong_count": 1,
                "created_at": datetime.utcnow(),
                "last_wrong_at": datetime.utcnow(),
                "mastered": False
            })

    @staticmethod
    async def get_session_progress(session_id: str, user_id: str) -> dict:
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        progress = PracticeService._build_progress(session)
        progress["answers"] = session.get("answers", {})
        return progress
