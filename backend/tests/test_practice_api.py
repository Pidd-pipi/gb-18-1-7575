"""通过 HTTP 层验证顺序刷题闭环：登录 → 开始 → 作答 → 恢复 → 完成归档。"""
import asyncio
from datetime import datetime, timedelta

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

import app.core.database as database
import app.core.redis as redis_module
from app.core.security import create_access_token, get_password_hash
from app.main import app


USER_ID = str(ObjectId())
SUBJECT_ID = str(ObjectId())
KNOWLEDGE_ID = str(ObjectId())


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def client():
    mock_db = AsyncMongoMockClient()["exam_platform_api_test"]
    database.db = mock_db
    redis_module.redis = None

    async def seed():
        await mock_db.users.insert_one({
            "_id": ObjectId(USER_ID),
            "username": "student",
            "email": "student@example.com",
            "hashed_password": get_password_hash("student123"),
            "role": "student",
            "created_at": datetime.utcnow(),
            "avatar": None,
            "stats": {"total_practiced": 0, "total_correct": 0, "streak_days": 0}
        })
        base = datetime(2024, 1, 1, 8, 0, 0)
        await mock_db.questions.insert_many([
            {
                "type": "single_choice",
                "content": f"第{i + 1}题",
                "options": [{"key": "A", "content": "甲"}, {"key": "B", "content": "乙"}],
                "correct_answer": "A",
                "explanation": f"解析{i + 1}",
                "subject_id": SUBJECT_ID,
                "knowledge_ids": [KNOWLEDGE_ID],
                "difficulty": "easy",
                "tags": [],
                "created_at": base + timedelta(minutes=i),
                "updated_at": base + timedelta(minutes=i),
                "stats": {"answered": 0, "correct": 0}
            }
            for i in range(3)
        ])

    run(seed())

    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    database.db = None
    redis_module.redis = None


def auth_headers():
    token = create_access_token(USER_ID)
    return {"Authorization": f"Bearer {token}"}


def test_full_sequential_practice_loop(client):
    async def scenario():
        headers = auth_headers()

        # 登录接口可用
        login_resp = await client.post("/api/auth/login", json={
            "username": "student", "password": "student123"
        })
        assert login_resp.status_code == 200, login_resp.text

        # 开始顺序练习：题序固定
        start_resp = await client.post("/api/practice/start", json={
            "mode": "sequential",
            "subject_id": SUBJECT_ID,
            "knowledge_ids": [KNOWLEDGE_ID],
            "question_count": 3
        }, headers=headers)
        assert start_resp.status_code == 200, start_resp.text
        started = start_resp.json()
        session_id = started["session_id"]
        first_question = started["current_question"]
        assert started["progress"]["total"] == 3
        assert started["progress"]["current"] == 0

        # 第 1 题答对，反馈包含正确答案与解析
        submit1 = await client.post("/api/practice/submit", json={
            "session_id": session_id,
            "question_id": first_question["id"],
            "user_answer": "A"
        }, headers=headers)
        assert submit1.status_code == 200, submit1.text
        r1 = submit1.json()
        assert r1["is_correct"] is True
        assert r1["correct_answer"] == "A"
        assert r1["explanation"] == "解析1"
        assert r1["progress"]["current"] == 1

        # 重复提交不覆盖既有结果
        dup = await client.post("/api/practice/submit", json={
            "session_id": session_id,
            "question_id": first_question["id"],
            "user_answer": "B"
        }, headers=headers)
        assert dup.status_code == 200
        assert dup.json()["is_correct"] is True
        assert dup.json()["progress"]["correct"] == 1

        # 跳题被拒绝
        q3 = (await client.get(f"/api/practice/question/{session_id}/2", headers=headers)).json()
        skip = await client.post("/api/practice/submit", json={
            "session_id": session_id,
            "question_id": q3["question"]["id"],
            "user_answer": "A"
        }, headers=headers)
        assert skip.status_code == 400

        # 第 2 题答错
        q2 = (await client.get(f"/api/practice/question/{session_id}/1", headers=headers)).json()
        submit2 = await client.post("/api/practice/submit", json={
            "session_id": session_id,
            "question_id": q2["question"]["id"],
            "user_answer": "B"
        }, headers=headers)
        assert submit2.json()["is_correct"] is False

        # 退出后通过 active 接口恢复到下一未完成题
        active = await client.get(
            f"/api/practice/active?mode=sequential&subject_id={SUBJECT_ID}&knowledge_id={KNOWLEDGE_ID}",
            headers=headers
        )
        assert active.status_code == 200
        assert active.json()["session_id"] == session_id
        assert active.json()["progress"]["current"] == 2

        resumed = await client.get(f"/api/practice/session/{session_id}", headers=headers)
        assert resumed.json()["current_question"]["id"] == q3["question"]["id"]

        # 答完最后一题：显示正确率
        submit3 = await client.post("/api/practice/submit", json={
            "session_id": session_id,
            "question_id": q3["question"]["id"],
            "user_answer": "A"
        }, headers=headers)
        r3 = submit3.json()
        assert r3["is_finished"] is True
        assert r3["progress"]["correct"] == 2
        assert r3["progress"]["accuracy"] == 66.7

        # 错题已归档
        errors = await client.get("/api/errors/list", headers=headers)
        assert errors.status_code == 200
        assert errors.json()["total"] == 1

        # 完成后 active 返回空，可重新开始
        active_after = await client.get(
            f"/api/practice/active?mode=sequential&subject_id={SUBJECT_ID}&knowledge_id={KNOWLEDGE_ID}",
            headers=headers
        )
        assert active_after.json() is None

    run(scenario())
