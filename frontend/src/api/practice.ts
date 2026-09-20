import request from './request'
import type {
  PracticeResult,
  PracticeSessionInfo,
  PracticeProgress,
  SessionQuestion
} from '@/types'

export const startPractice = (data: {
  mode: string
  subject_id: string
  knowledge_ids?: string[]
  question_count: number
  difficulty?: string
}) => {
  return request.post<PracticeSessionInfo>('/practice/start', data)
}

export const submitAnswer = (sessionId: string, questionId: string, userAnswer: any) => {
  return request.post<PracticeResult>('/practice/submit', {
    session_id: sessionId,
    question_id: questionId,
    user_answer: userAnswer
  })
}

export const getPracticeSession = (sessionId: string) => {
  return request.get<PracticeSessionInfo>(`/practice/session/${sessionId}`)
}

export const getActiveSession = (params: {
  mode: string
  subject_id: string
  knowledge_id?: string
}) => {
  return request.get<PracticeSessionInfo | null>('/practice/active', { params })
}

export const getSessionQuestion = (sessionId: string, index: number) => {
  return request.get<SessionQuestion>(`/practice/question/${sessionId}/${index}`)
}

export const getPracticeProgress = (sessionId: string) => {
  return request.get<PracticeProgress & { answers: Record<string, any> }>(
    `/practice/progress/${sessionId}`
  )
}
