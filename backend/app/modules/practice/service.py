from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
import json
import logging
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.questions.service import QuestionService

logger = logging.getLogger(__name__)

SESSION_CACHE_TTL = 3600 * 24


class PracticeService:
    """顺序练习闭环：固定题序、幂等提交、断点恢复、完成归档。"""

    # ---------- Redis 缓存（仅加速，MongoDB 为权威存储，缓存失败不影响流程） ----------

    @staticmethod
    def _cache_key(user_id: str, session_id: str) -> str:
        return f"practice:{user_id}:{session_id}"

    @staticmethod
    async def _cache_session(user_id: str, session: dict):
        try:
            redis = get_redis()
            if redis:
                await redis.setex(
                    PracticeService._cache_key(user_id, session["id"]),
                    SESSION_CACHE_TTL,
                    json.dumps(session, default=str)
                )
        except Exception as e:
            logger.warning(f"练习会话缓存写入失败（不影响保存）: {e}")

    @staticmethod
    async def _drop_cached_session(user_id: str, session_id: str):
        try:
            redis = get_redis()
            if redis:
                await redis.delete(PracticeService._cache_key(user_id, session_id))
        except Exception:
            pass

    # ---------- 会话创建与恢复 ----------

    @staticmethod
    async def create_session(
        user_id: str,
        mode: str,
        subject_id: Optional[str] = None,
        knowledge_ids: Optional[List[str]] = None,
        question_count: int = 20,
        difficulty: Optional[str] = None
    ) -> dict:
        db = get_db()

        # 相同配置的未完成会话直接恢复，退出后能从下一未完成题继续
        existing = await db.practice_sessions.find_one(
            {
                "user_id": user_id,
                "mode": mode,
                "subject_id": subject_id,
                "knowledge_ids": knowledge_ids,
                "question_count": question_count,
                "difficulty": difficulty,
                "status": "in_progress"
            },
            sort=[("created_at", -1)]
        )
        if existing:
            existing["id"] = str(existing["_id"])
            existing["_id"] = str(existing["_id"])
            await PracticeService._cache_session(user_id, existing)
            return existing

        if mode == "random":
            if not subject_id:
                raise ValueError("随机练习需要指定学科")
            questions = await QuestionService.get_random_questions(
                subject_id=subject_id,
                knowledge_ids=knowledge_ids,
                difficulty=difficulty,
                count=question_count
            )
        elif mode == "error_practice":
            from app.modules.errors.service import ErrorService
            knowledge_id = knowledge_ids[0] if knowledge_ids else None
            error_question_ids = await ErrorService.get_errors_for_practice(
                user_id, knowledge_id, question_count
            )
            questions = await QuestionService.get_questions_by_ids(error_question_ids)
        else:
            # 顺序练习：按知识点固定题序（创建时间 + 主键排序，保证顺序稳定）
            if not subject_id:
                raise ValueError("顺序练习需要指定学科")
            query: Dict[str, Any] = {"subject_id": subject_id}
            if knowledge_ids:
                query["knowledge_ids"] = {"$in": knowledge_ids}
            if difficulty:
                query["difficulty"] = difficulty
            cursor = db.questions.find(query).sort(
                [("created_at", 1), ("_id", 1)]
            ).limit(question_count)
            questions = await cursor.to_list(length=question_count)

        if not questions:
            raise ValueError("没有找到符合条件的题目")

        # 题序在会话创建时固化，之后的提交、跳题、题序变化都不影响既有结果
        question_ids = [str(q["_id"]) for q in questions]
        now = datetime.utcnow()
        session_dict = {
            "user_id": user_id,
            "mode": mode,
            "subject_id": subject_id,
            "knowledge_ids": knowledge_ids,
            "question_count": question_count,
            "difficulty": difficulty,
            "question_ids": question_ids,
            "current_index": 0,
            "answers": {},
            "total": len(question_ids),
            "correct_count": 0,
            "status": "in_progress",
            "final_accuracy": None,
            "created_at": now,
            "updated_at": now,
            "finished_at": None
        }

        result = await db.practice_sessions.insert_one(session_dict)
        session_dict["_id"] = str(result.inserted_id)
        session_dict["id"] = str(result.inserted_id)

        await PracticeService._cache_session(user_id, session_dict)
        return session_dict

    @staticmethod
    async def get_session(session_id: str, user_id: str) -> Optional[dict]:
        db = get_db()

        cached = await PracticeService._read_cached_session(user_id, session_id)
        if cached:
            return cached

        if not ObjectId.is_valid(session_id):
            return None
        session = await db.practice_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id
        })

        if session:
            session["id"] = str(session["_id"])
            session["_id"] = str(session["_id"])
            await PracticeService._cache_session(user_id, session)

        return session

    @staticmethod
    async def _read_cached_session(user_id: str, session_id: str) -> Optional[dict]:
        try:
            redis = get_redis()
            if redis:
                cached = await redis.get(PracticeService._cache_key(user_id, session_id))
                if cached:
                    return json.loads(cached)
        except Exception as e:
            logger.warning(f"练习会话缓存读取失败，回退数据库: {e}")
        return None

    @staticmethod
    async def get_current_question(session: dict) -> Optional[dict]:
        current_index = session.get("current_index", 0)
        question_ids = session.get("question_ids", [])
        if 0 <= current_index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[current_index])
        return None

    # ---------- 提交（每次提交只接受一次） ----------

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
        current_index = session.get("current_index", 0)
        answers = session.get("answers", {})

        # 重复提交：直接回读既有结果，不覆盖、不计分、不改位置
        if question_id in answers:
            return PracticeService._build_submit_result(
                session, question_id, answers[question_id], replayed=True
            )

        if current_index >= len(question_ids):
            raise ValueError("本次练习已完成，无法继续提交")

        # 跳题或题序变化：只允许作答当前位置的题目
        if question_ids[current_index] != question_id:
            raise ValueError("请按顺序作答当前题目")

        question = await QuestionService.get_question_by_id(question_id)
        if not question:
            raise ValueError("题目不存在")

        is_correct = QuestionService.compare_answers(
            question["type"], user_answer, question["correct_answer"]
        )

        now = datetime.utcnow()
        # 正确答案、解析随作答记录一起保存
        record = {
            "user_answer": user_answer,
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "explanation": question.get("explanation"),
            "submitted_at": now.isoformat()
        }

        new_index = current_index + 1
        correct_count = session.get("correct_count", 0) + (1 if is_correct else 0)
        is_finished = new_index >= len(question_ids)

        # 得分与下一题位置在同一次原子写入中保存；
        # 过滤条件保证并发/重复提交只有第一次能写入
        update_data: Dict[str, Any] = {
            f"answers.{question_id}": record,
            "correct_count": correct_count,
            "current_index": new_index,
            "updated_at": now
        }
        if is_finished:
            update_data["status"] = "finished"
            update_data["finished_at"] = now
            update_data["final_accuracy"] = round(
                correct_count / len(question_ids) * 100, 1
            ) if question_ids else 0

        update_result = await db.practice_sessions.update_one(
            {
                "_id": ObjectId(session_id),
                "user_id": user_id,
                "current_index": current_index,
                f"answers.{question_id}": {"$exists": False}
            },
            {"$set": update_data}
        )

        if update_result.matched_count == 0:
            # 并发重复提交：以数据库中已有结果为准
            fresh = await db.practice_sessions.find_one({"_id": ObjectId(session_id)})
            if fresh and question_id in fresh.get("answers", {}):
                fresh["id"] = str(fresh["_id"])
                fresh["_id"] = str(fresh["_id"])
                await PracticeService._cache_session(user_id, fresh)
                return PracticeService._build_submit_result(
                    fresh, question_id, fresh["answers"][question_id], replayed=True
                )
            raise ValueError("提交冲突，请刷新后重试")

        # 首次接受后才更新题目统计，避免重复提交虚增答题量
        await QuestionService.record_answer_stats(question_id, is_correct)

        # 答错归档到错题本
        if not is_correct:
            await PracticeService._add_to_errors(user_id, question_id)

        session["answers"] = {**answers, question_id: record}
        session["correct_count"] = correct_count
        session["current_index"] = new_index
        session["updated_at"] = now
        if is_finished:
            session["status"] = "finished"
            session["finished_at"] = now
            session["final_accuracy"] = update_data["final_accuracy"]
        await PracticeService._cache_session(user_id, session)

        return PracticeService._build_submit_result(
            session, question_id, record, replayed=False
        )

    @staticmethod
    def _build_submit_result(
        session: dict,
        question_id: str,
        record: dict,
        replayed: bool
    ) -> Dict[str, Any]:
        total = session.get("total", 0)
        answered = len(session.get("answers", {}))
        correct = session.get("correct_count", 0)
        current_index = session.get("current_index", 0)
        is_finished = session.get("status") == "finished" or current_index >= total

        return {
            "question_id": question_id,
            "is_correct": record.get("is_correct"),
            "correct_answer": record.get("correct_answer"),
            "explanation": record.get("explanation"),
            "progress": {
                "current": current_index,
                "total": total,
                "correct": correct,
                "accuracy": round(correct / answered * 100, 1) if answered else 0
            },
            "next_index": current_index,
            "is_finished": is_finished,
            "final_accuracy": session.get("final_accuracy"),
            "replayed": replayed
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

    # ---------- 只读访问（上一题/下一题浏览不改变进度指针） ----------

    @staticmethod
    async def get_question_at(
        session_id: str,
        user_id: str,
        index: int
    ) -> Dict[str, Any]:
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
            "question": PracticeService.public_question(question),
            "record": record,
            "index": index,
            "progress": PracticeService.build_progress(session)
        }

    @staticmethod
    def public_question(question: dict) -> dict:
        """题目公开信息，未作答前不泄露正确答案与解析。"""
        return {
            "id": str(question["_id"]),
            "type": question["type"],
            "content": question["content"],
            "options": question.get("options"),
            "difficulty": question["difficulty"],
            "knowledge_ids": question.get("knowledge_ids", [])
        }

    @staticmethod
    def build_progress(session: dict) -> Dict[str, Any]:
        answers = session.get("answers", {})
        correct_count = sum(1 for a in answers.values() if a.get("is_correct"))
        return {
            "current": session.get("current_index", 0),
            "total": session.get("total", 0),
            "correct": correct_count,
            "accuracy": round(correct_count / len(answers) * 100, 1) if answers else 0
        }

    @staticmethod
    def build_session_payload(session: dict, current_question: Optional[dict]) -> Dict[str, Any]:
        total = session.get("total", 0)
        current_index = session.get("current_index", 0)
        is_finished = session.get("status") == "finished" or current_index >= total
        return {
            "session_id": session["id"],
            "mode": session.get("mode"),
            "current_question": PracticeService.public_question(current_question) if current_question else None,
            "progress": PracticeService.build_progress(session),
            "answers": session.get("answers", {}),
            "is_finished": is_finished,
            "final_accuracy": session.get("final_accuracy")
        }

    @staticmethod
    async def get_session_progress(session_id: str, user_id: str) -> dict:
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        progress = PracticeService.build_progress(session)
        return {
            **progress,
            "answers": session.get("answers", {}),
            "is_finished": session.get("status") == "finished"
                or session.get("current_index", 0) >= session.get("total", 0),
            "final_accuracy": session.get("final_accuracy")
        }
