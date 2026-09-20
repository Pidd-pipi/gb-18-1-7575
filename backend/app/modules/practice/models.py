from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel


class PracticeConfig(BaseModel):
    mode: str
    subject_id: str
    knowledge_ids: Optional[List[str]] = None
    question_count: int = 20
    difficulty: Optional[str] = None


class PracticeQuestion(BaseModel):
    id: str
    type: str
    content: str
    options: Optional[List[dict]] = None
    difficulty: str
    knowledge_ids: List[str]


class AnswerRecord(BaseModel):
    user_answer: Any
    is_correct: bool
    correct_answer: Any
    explanation: Optional[str] = None
    submitted_at: Optional[str] = None


class PracticeSession(BaseModel):
    id: str
    mode: str
    subject_id: str
    knowledge_ids: Optional[List[str]]
    question_ids: List[str]
    current_index: int
    answers: dict
    total: int
    correct_count: int
    status: str = "in_progress"
    created_at: datetime
    updated_at: datetime


class PracticeSubmit(BaseModel):
    session_id: str
    question_id: str
    user_answer: Any


class PracticeResult(BaseModel):
    question_id: str
    is_correct: bool
    correct_answer: Any
    explanation: Optional[str]
    progress: dict
    is_finished: bool = False
