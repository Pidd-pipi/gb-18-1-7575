import request from './request'
import type {
  PracticeResult,
  PracticeStartResult,
  SessionQuestion
} from '@/types'

export const startPractice = (data: {
  mode: string
  subject_id?: string
  knowledge_ids?: string[]
  question_count: number
  difficulty?: string
}) => {
  return request.post<PracticeStartResult>('/practice/start', data)
}

export const submitAnswer = (sessionId: string, questionId: string, userAnswer: any) => {
  return request.post<PracticeResult>('/practice/submit', {
    session_id: sessionId,
    question_id: questionId,
    user_answer: userAnswer
  })
}

export const getPracticeSession = (sessionId: string) => {
  return request.get<PracticeStartResult>(`/practice/session/${sessionId}`)
}

export const getQuestionAt = (sessionId: string, index: number) => {
  return request.get<SessionQuestion>(`/practice/session/${sessionId}/question/${index}`)
}

export const getSessionProgress = (sessionId: string) => {
  return request.get<{
    current: number
    total: number
    correct: number
    accuracy: number
    answers: Record<string, any>
    is_finished: boolean
    final_accuracy: number | null
  }>(`/practice/progress/${sessionId}`)
}
