"""顺序刷题闭环测试：固定题序、幂等提交、防跳题、进度恢复、完成归档。"""
import asyncio
from datetime import datetime, timedelta

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

import app.core.database as database
import app.core.redis as redis_module
from app.modules.practice.service import PracticeService


class FakeRedis:
    """模拟 Redis 行为，验证缓存读写路径（含 datetime 序列化）。"""

    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


USER_ID = "user-1"
SUBJECT_ID = "subject-1"
KNOWLEDGE_ID = "knowledge-1"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def db():
    client = AsyncMongoMockClient()
    mock_db = client["exam_platform_test"]
    database.db = mock_db
    redis_module.redis = None
    yield mock_db
    database.db = None
    redis_module.redis = None


@pytest.fixture()
def fake_redis(db):
    redis_module.redis = FakeRedis()
    yield redis_module.redis
    redis_module.redis = None


def seed_questions(db, count=5):
    async def _seed():
        base = datetime(2024, 1, 1, 8, 0, 0)
        docs = []
        for i in range(count):
            docs.append({
                "type": "single_choice",
                "content": f"第{i + 1}题",
                "options": [
                    {"key": "A", "content": "选项A"},
                    {"key": "B", "content": "选项B"}
                ],
                "correct_answer": "A",
                "explanation": f"第{i + 1}题解析",
                "subject_id": SUBJECT_ID,
                "knowledge_ids": [KNOWLEDGE_ID],
                "difficulty": "easy",
                "tags": [],
                "created_at": base + timedelta(minutes=i),
                "updated_at": base + timedelta(minutes=i),
                "stats": {"answered": 0, "correct": 0}
            })
        result = await db.questions.insert_many(docs)
        return [str(qid) for qid in result.inserted_ids]
    return run(_seed())


def create_session(question_count=5):
    return run(PracticeService.create_session(
        user_id=USER_ID,
        mode="sequential",
        subject_id=SUBJECT_ID,
        knowledge_ids=[KNOWLEDGE_ID],
        question_count=question_count
    ))


def submit(session_id, question_id, answer):
    return run(PracticeService.submit_answer(
        session_id=session_id,
        user_id=USER_ID,
        question_id=question_id,
        user_answer=answer
    ))


def test_sequential_order_is_fixed(db):
    question_ids = seed_questions(db)
    s1 = create_session()
    s2 = create_session()
    assert s1["question_ids"] == question_ids
    assert s2["question_ids"] == question_ids


def test_submit_saves_answer_score_and_next_position(db):
    seed_questions(db)
    session = create_session()
    qid = session["question_ids"][0]

    result = submit(session["id"], qid, "A")
    assert result["is_correct"] is True
    assert result["correct_answer"] == "A"
    assert result["explanation"] == "第1题解析"
    assert result["progress"]["current"] == 1
    assert result["progress"]["correct"] == 1
    assert result["is_finished"] is False

    stored = run(db.practice_sessions.find_one({"_id": ObjectId(session["id"])}))
    assert stored["current_index"] == 1
    assert stored["correct_count"] == 1
    record = stored["answers"][qid]
    assert record["user_answer"] == "A"
    assert record["is_correct"] is True
    assert record["correct_answer"] == "A"
    assert record["explanation"] == "第1题解析"
    assert record["submitted_at"]


def test_duplicate_submit_returns_stored_result_without_overwrite(db):
    seed_questions(db)
    session = create_session()
    qid = session["question_ids"][0]

    first = submit(session["id"], qid, "B")  # 答错
    assert first["is_correct"] is False

    # 重复提交不同答案：不得覆盖既有结果
    second = submit(session["id"], qid, "A")
    assert second["is_correct"] is False
    assert second["user_answer"] == "B"
    assert second["submitted_at"] == first["submitted_at"]
    assert second["progress"]["current"] == 1
    assert second["progress"]["correct"] == 0

    # 错题只归档一次
    error = run(db.errors.find_one({"user_id": USER_ID, "question_id": qid}))
    assert error["wrong_count"] == 1


def test_skip_question_is_rejected(db):
    seed_questions(db)
    session = create_session()
    second_qid = session["question_ids"][1]

    with pytest.raises(ValueError, match="按顺序作答"):
        submit(session["id"], second_qid, "A")

    progress = run(PracticeService.get_session_progress(session["id"], USER_ID))
    assert progress["current"] == 0
    assert progress["answered"] == 0


def test_resume_from_next_unfinished_question(db):
    seed_questions(db)
    session = create_session()
    submit(session["id"], session["question_ids"][0], "A")
    submit(session["id"], session["question_ids"][1], "B")

    active = run(PracticeService.get_active_session(
        user_id=USER_ID,
        mode="sequential",
        subject_id=SUBJECT_ID,
        knowledge_ids=[KNOWLEDGE_ID]
    ))
    assert active is not None
    assert active["id"] == session["id"]
    assert active["current_index"] == 2

    current = run(PracticeService.get_current_question(active))
    assert str(current["_id"]) == session["question_ids"][2]


def test_progress_survives_cache_loss(db, fake_redis):
    """服务重启（缓存清空）后仍能从 MongoDB 回读进度。"""
    seed_questions(db)
    session = create_session()
    submit(session["id"], session["question_ids"][0], "A")
    submit(session["id"], session["question_ids"][1], "B")

    fake_redis.store.clear()  # 模拟服务重启导致缓存丢失

    restored = run(PracticeService.get_session(session["id"], USER_ID))
    assert restored is not None
    assert restored["current_index"] == 2
    assert restored["correct_count"] == 1
    assert len(restored["answers"]) == 2

    progress = run(PracticeService.get_session_progress(session["id"], USER_ID))
    assert progress["accuracy"] == 50.0


def test_navigation_is_read_only(db):
    seed_questions(db)
    session = create_session()
    submit(session["id"], session["question_ids"][0], "A")

    viewed = run(PracticeService.get_question_at(session["id"], USER_ID, 0))
    assert viewed["record"]["is_correct"] is True
    assert viewed["record"]["correct_answer"] == "A"

    future = run(PracticeService.get_question_at(session["id"], USER_ID, 1))
    assert future["record"] is None

    # 回看已答题不改变下一题位置
    progress = run(PracticeService.get_session_progress(session["id"], USER_ID))
    assert progress["current"] == 1


def test_finish_shows_accuracy_and_archives_errors(db):
    seed_questions(db)
    session = create_session()
    answers = ["A", "B", "A", "B", "A"]  # 3 对 2 错

    result = None
    for qid, ans in zip(session["question_ids"], answers):
        result = submit(session["id"], qid, ans)

    assert result["is_finished"] is True
    assert result["progress"]["correct"] == 3
    assert result["progress"]["accuracy"] == 60.0

    stored = run(db.practice_sessions.find_one({"_id": __import__("bson").ObjectId(session["id"])}))
    assert stored["status"] == "finished"
    assert stored["finished_at"] is not None

    # 错题全部归档
    errors = run(db.errors.find({"user_id": USER_ID}).to_list(length=None))
    assert len(errors) == 2

    # 完成后不再有未完成会话
    active = run(PracticeService.get_active_session(
        user_id=USER_ID,
        mode="sequential",
        subject_id=SUBJECT_ID,
        knowledge_ids=[KNOWLEDGE_ID]
    ))
    assert active is None

    # 完成后不能再提交新答案
    with pytest.raises(ValueError):
        submit(session["id"], "not-a-question", "A")


def test_cache_roundtrip_with_datetime(db, fake_redis):
    """Redis 可用时，创建/提交/读取全链路不因 datetime 崩溃。"""
    seed_questions(db)
    session = create_session()
    assert fake_redis.store  # 已写入缓存

    result = submit(session["id"], session["question_ids"][0], "A")
    assert result["is_correct"] is True

    cached = run(PracticeService.get_session(session["id"], USER_ID))
    assert cached["current_index"] == 1
    assert cached["answers"][session["question_ids"][0]]["is_correct"] is True


def test_concurrent_submit_first_write_wins(db, monkeypatch):
    """并发重复提交：数据库层面只接受首次写入，后来的请求回读已保存结果。"""
    seed_questions(db)
    session = create_session()
    qid = session["question_ids"][0]

    first = submit(session["id"], qid, "A")
    assert first["is_correct"] is True

    # 模拟竞态：第二个请求读到的是提交前的旧会话快照
    async def stale_get_session(session_id, user_id):
        stale = dict(session)
        stale["answers"] = {}
        return stale

    monkeypatch.setattr(
        PracticeService, "get_session", staticmethod(stale_get_session)
    )
    second = submit(session["id"], qid, "B")  # 不同答案，不得覆盖

    assert second["is_correct"] is True
    assert second["user_answer"] == "A"
    assert second["progress"]["correct"] == 1
