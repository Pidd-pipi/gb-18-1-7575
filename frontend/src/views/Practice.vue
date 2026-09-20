<template>
  <div class="practice-page">
    <van-nav-bar
      :title="modeName"
      left-arrow
      @click-left="handleBack"
    >
      <template #right>
        <span v-if="progress.total > 0" class="nav-progress">{{ displayIndex }} / {{ progress.total }}</span>
        <van-icon
          v-else-if="mode !== 'error_practice'"
          name="exchange"
          class="nav-switch"
          @click="openPicker"
        />
      </template>
    </van-nav-bar>

    <div v-if="progress.total > 0 && !showSummary" class="progress-header">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-stats">
        <span>正确率 {{ progress.accuracy }}%</span>
        <span>已对 {{ progress.correct }} 题</span>
      </div>
    </div>

    <div class="question-container" v-if="currentQuestion && !showSummary">
      <div class="question-header">
        <span class="question-type">{{ questionTypeLabel }}</span>
        <span class="difficulty-tag" :class="'difficulty-' + currentQuestion.difficulty">
          {{ difficultyLabel }}
        </span>
      </div>

      <div class="question-content">
        {{ currentQuestion.content }}
      </div>

      <div v-if="!showResult" class="options-container">
        <div
          v-if="currentQuestion.type === 'fill_blank'"
          class="fill-blank-container"
        >
          <van-field
            v-model="fillAnswer"
            placeholder="请输入答案"
            :border="false"
            class="fill-input"
          />
        </div>

        <template v-else>
          <div
            v-for="option in displayOptions"
            :key="option.key"
            class="option-item"
            :class="{ selected: isOptionSelected(option.key) }"
            @click="selectOption(option.key)"
          >
            <span class="option-key">{{ option.key }}</span>
            <span class="option-content">{{ option.content }}</span>
          </div>
        </template>
      </div>

      <div v-if="showResult" class="result-container">
        <div class="options-container">
          <template v-if="currentQuestion.type !== 'fill_blank'">
            <div
              v-for="option in displayOptions"
              :key="option.key"
              class="option-item"
              :class="getOptionClass(option.key)"
            >
              <span class="option-key">{{ option.key }}</span>
              <span class="option-content">{{ option.content }}</span>
            </div>
          </template>

          <div v-else class="fill-result">
            <div class="result-row">
              <span class="result-label">你的答案：</span>
              <span class="result-value" :class="currentRecord?.is_correct ? 'correct' : 'wrong'">
                {{ currentRecord?.user_answer || '未作答' }}
              </span>
            </div>
            <div class="result-row">
              <span class="result-label">正确答案：</span>
              <span class="result-value correct">{{ currentRecord?.correct_answer }}</span>
            </div>
          </div>
        </div>

        <div class="result-badge" :class="currentRecord?.is_correct ? 'correct' : 'wrong'">
          {{ currentRecord?.is_correct ? '✓ 回答正确' : '✗ 回答错误' }}
        </div>

        <div v-if="currentRecord?.explanation" class="explanation-box">
          <div class="explanation-title">解析</div>
          <div class="explanation-content">{{ currentRecord.explanation }}</div>
        </div>
      </div>
    </div>

    <div v-if="showSummary" class="finished-container">
      <div class="score-circle">
        <div class="score-value">{{ summaryAccuracy }}</div>
        <div class="score-label">正确率</div>
      </div>

      <div class="finished-stats">
        <div class="stat-item">
          <div class="stat-value">{{ progress.total }}</div>
          <div class="stat-label">总题数</div>
        </div>
        <div class="stat-item">
          <div class="stat-value correct">{{ progress.correct }}</div>
          <div class="stat-label">答对</div>
        </div>
        <div class="stat-item">
          <div class="stat-value wrong">{{ progress.total - progress.correct }}</div>
          <div class="stat-label">答错</div>
        </div>
      </div>

      <div v-if="progress.total - progress.correct > 0" class="archive-hint">
        错题已自动归档到错题本，可随时回顾重练
      </div>

      <div class="finished-actions">
        <van-button type="primary" block round @click="restart">
          再练一次
        </van-button>
        <van-button
          v-if="progress.total - progress.correct > 0"
          block
          round
          @click="goErrorBook"
        >
          查看错题本
        </van-button>
        <van-button block round @click="goBackToSubject">
          返回
        </van-button>
      </div>
    </div>

    <div v-if="!currentQuestion && !showSummary && !loading" class="empty-container">
      <van-empty description="请选择知识点开始练习">
        <van-button type="primary" round @click="openPicker">选择知识点</van-button>
      </van-empty>
    </div>

    <div class="nav-bottom" v-if="currentQuestion && !showSummary">
      <van-button
        plain
        size="large"
        :disabled="viewIndex === 0"
        @click="goPrev"
      >
        上一题
      </van-button>

      <van-button
        type="primary"
        size="large"
        :loading="submitting"
        :disabled="!showResult && !hasAnswer"
        @click="handlePrimary"
      >
        {{ primaryButtonText }}
      </van-button>
    </div>

    <van-popup
      v-model:show="showPicker"
      position="bottom"
      :style="{ height: '70%' }"
      round
    >
      <div class="picker">
        <div class="picker-header">
          <div class="picker-title">选择知识点</div>
          <van-icon name="cross" @click="showPicker = false" />
        </div>

        <div class="picker-body">
          <div class="picker-label">学科</div>
          <div class="subject-chips">
            <span
              v-for="subject in subjects"
              :key="subject.id"
              class="chip"
              :class="{ active: pickerSubjectId === subject.id }"
              @click="selectPickerSubject(subject.id)"
            >
              {{ subject.icon }} {{ subject.name }}
            </span>
          </div>

          <div class="picker-label">知识点</div>
          <div v-if="pickerLoading" class="loading-container">
            <van-loading />
          </div>
          <div v-else class="knowledge-list">
            <div
              class="knowledge-option"
              :class="{ active: pickerKnowledgeId === '' }"
              @click="pickerKnowledgeId = ''"
            >
              <span class="knowledge-name">全部题目</span>
            </div>
            <div
              v-for="node in knowledgeOptions"
              :key="node.id"
              class="knowledge-option"
              :class="{ active: pickerKnowledgeId === node.id }"
              @click="pickerKnowledgeId = node.id"
            >
              <span class="knowledge-name">{{ node.path }}</span>
              <span class="knowledge-count">{{ node.question_count }} 题</span>
            </div>
            <div v-if="knowledgeOptions.length === 0" class="empty-tip">
              该学科下暂无知识点
            </div>
          </div>
        </div>

        <div class="picker-footer">
          <van-button block type="primary" round @click="confirmPicker">
            开始练习
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showLoadingToast, closeToast, showToast } from 'vant'
import {
  startPractice,
  submitAnswer,
  getPracticeSession,
  getActiveSession,
  getSessionQuestion
} from '@/api/practice'
import { startErrorPractice } from '@/api/errors'
import { getSubjects, getKnowledgeTree, getKnowledgeNode } from '@/api/knowledge'
import type {
  Question,
  AnswerRecord,
  PracticeSessionInfo,
  Subject,
  KnowledgeNode
} from '@/types'

const route = useRoute()
const router = useRouter()

const mode = computed(() => route.params.mode as string)
const query = computed(() => route.query)

const sessionId = ref('')
const viewIndex = ref(0)
const currentQuestion = ref<Question | null>(null)
const currentRecord = ref<AnswerRecord | null>(null)
const selectedAnswer = ref<any>(null)
const selectedAnswers = ref<string[]>([])
const fillAnswer = ref('')
const showSummary = ref(false)
const submitting = ref(false)
const loading = ref(false)

const scope = reactive({
  subjectId: '',
  knowledgeId: ''
})

const progress = reactive({
  current: 0,
  total: 0,
  correct: 0,
  accuracy: 0,
  status: 'in_progress'
})

const showPicker = ref(false)
const subjects = ref<Subject[]>([])
const pickerSubjectId = ref('')
const pickerKnowledgeId = ref('')
const knowledgeOptions = ref<{ id: string; path: string; question_count: number }[]>([])
const pickerLoading = ref(false)

const modeName = computed(() => {
  const modeMap: Record<string, string> = {
    sequential: '顺序练习',
    random: '随机练习',
    error_practice: '错题重练'
  }
  return modeMap[mode.value] || '练习'
})

const showResult = computed(() => currentRecord.value !== null)

const isFinished = computed(() => progress.status === 'finished')

const displayIndex = computed(() => Math.min(viewIndex.value + 1, progress.total))

const progressPercent = computed(() => {
  if (!progress.total) return 0
  return Math.round((progress.current / progress.total) * 100)
})

const summaryAccuracy = computed(() => {
  if (!progress.total) return 0
  return Math.round((progress.correct / progress.total) * 1000) / 10
})

const questionTypeLabel = computed(() => {
  const typeMap: Record<string, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题'
  }
  return typeMap[currentQuestion.value?.type || ''] || '题目'
})

const difficultyLabel = computed(() => {
  const diffMap: Record<string, string> = {
    easy: '简单',
    medium: '中等',
    hard: '困难'
  }
  return diffMap[currentQuestion.value?.difficulty || ''] || ''
})

// 判断题没有选项数据时，使用默认的对/错选项
const displayOptions = computed(() => {
  const q = currentQuestion.value
  if (!q) return []
  if (q.options && q.options.length > 0) return q.options
  if (q.type === 'true_false') {
    return [
      { key: 'A', content: '正确' },
      { key: 'B', content: '错误' }
    ]
  }
  return []
})

const hasAnswer = computed(() => {
  if (!currentQuestion.value) return false
  if (currentQuestion.value.type === 'fill_blank') return !!fillAnswer.value.trim()
  if (currentQuestion.value.type === 'multiple_choice') return selectedAnswers.value.length > 0
  return selectedAnswer.value !== null && selectedAnswer.value !== undefined
})

const primaryButtonText = computed(() => {
  if (!showResult.value) return '提交答案'
  if (isFinished.value && viewIndex.value >= progress.total - 1) return '查看结果'
  return '下一题'
})

const storageKey = () =>
  `practice_session:${mode.value}:${scope.subjectId}:${scope.knowledgeId || 'all'}`

const isOptionSelected = (key: string) => {
  if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value.includes(key)
  }
  return selectedAnswer.value === key
}

const getOptionClass = (key: string) => {
  const classes: string[] = []
  const correct = currentRecord.value?.correct_answer
  const isCorrectKey = Array.isArray(correct) ? correct.includes(key) : key === correct
  if (isCorrectKey) {
    classes.push('correct')
  } else if (isOptionSelected(key) && !currentRecord.value?.is_correct) {
    classes.push('wrong')
  }
  return classes
}

const selectOption = (key: string) => {
  if (showResult.value) return

  if (currentQuestion.value?.type === 'multiple_choice') {
    const index = selectedAnswers.value.indexOf(key)
    if (index > -1) {
      selectedAnswers.value.splice(index, 1)
    } else {
      selectedAnswers.value.push(key)
    }
    selectedAnswers.value.sort()
  } else {
    selectedAnswer.value = key
  }
}

const getAnswerToSubmit = () => {
  if (currentQuestion.value?.type === 'fill_blank') {
    return fillAnswer.value.trim()
  } else if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value
  }
  return selectedAnswer.value
}

const applyRecordToInputs = (record: AnswerRecord | null) => {
  selectedAnswer.value = null
  selectedAnswers.value = []
  fillAnswer.value = ''
  if (!record) return
  if (Array.isArray(record.user_answer)) {
    selectedAnswers.value = [...record.user_answer]
  } else if (currentQuestion.value?.type === 'fill_blank') {
    fillAnswer.value = record.user_answer ?? ''
  } else {
    selectedAnswer.value = record.user_answer
  }
}

const loadQuestion = async (index: number) => {
  const data = await getSessionQuestion(sessionId.value, index)
  currentQuestion.value = data.question
  currentRecord.value = data.record
  viewIndex.value = data.index
  applyRecordToInputs(data.record)
}

const applyProgress = (p: {
  current: number
  total: number
  correct: number
  accuracy: number
  status: string
}) => {
  progress.current = p.current
  progress.total = p.total
  progress.correct = p.correct
  progress.accuracy = p.accuracy
  progress.status = p.status
}

const applySession = async (info: PracticeSessionInfo) => {
  sessionId.value = info.session_id
  applyProgress(info.progress)
  if (mode.value === 'sequential') {
    localStorage.setItem(storageKey(), info.session_id)
  }
  if (info.progress.status === 'finished') {
    showSummary.value = true
    currentQuestion.value = null
    return
  }
  await loadQuestion(info.progress.current)
}

const startNew = async () => {
  const knowledgeIds = scope.knowledgeId ? [scope.knowledgeId] : undefined
  const result = await startPractice({
    mode: mode.value,
    subject_id: scope.subjectId,
    knowledge_ids: knowledgeIds,
    question_count: parseInt(query.value.count as string) || 20,
    difficulty: (query.value.difficulty as string) || undefined
  })
  showSummary.value = false
  await applySession(result)
}

const restoreOrStart = async () => {
  // 顺序练习：优先恢复未完成的会话（本地记录 → 服务端查找）
  if (mode.value === 'sequential') {
    const savedId = localStorage.getItem(storageKey())
    if (savedId) {
      try {
        const info = await getPracticeSession(savedId)
        if (info.status === 'in_progress') {
          await applySession(info)
          return
        }
      } catch (error) {
        localStorage.removeItem(storageKey())
      }
    }

    try {
      const active = await getActiveSession({
        mode: mode.value,
        subject_id: scope.subjectId,
        knowledge_id: scope.knowledgeId || undefined
      })
      if (active) {
        await applySession(active)
        return
      }
    } catch (error) {
      console.error(error)
    }
  }

  await startNew()
}

const startErrorSession = async () => {
  const result = await startErrorPractice({
    question_count: parseInt(query.value.count as string) || 20
  })
  if (!result.session_id) {
    showToast(result.message || '没有错题需要练习')
    setTimeout(() => router.push('/errors'), 800)
    return
  }
  sessionId.value = result.session_id
  applyProgress({
    current: result.progress.current,
    total: result.progress.total,
    correct: result.progress.correct,
    accuracy: result.progress.accuracy,
    status: 'in_progress'
  })
  await loadQuestion(0)
}

const initPractice = async () => {
  loading.value = true
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    if (mode.value === 'error_practice') {
      await startErrorSession()
      return
    }

    scope.subjectId = (query.value.subjectId as string) || ''
    scope.knowledgeId = (query.value.knowledgeIds as string) || ''

    // 只有知识点没有学科时，先反查所属学科
    if (!scope.subjectId && scope.knowledgeId) {
      try {
        const node = await getKnowledgeNode(scope.knowledgeId)
        scope.subjectId = node.subject_id
      } catch (error) {
        console.error(error)
      }
    }

    if (!scope.subjectId) {
      await openPicker()
      return
    }

    await restoreOrStart()
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
    closeToast()
  }
}

const handleSubmit = async () => {
  if (!hasAnswer.value || !currentQuestion.value) return

  submitting.value = true
  try {
    const result = await submitAnswer(
      sessionId.value,
      currentQuestion.value.id,
      getAnswerToSubmit()
    )
    currentRecord.value = {
      user_answer: result.user_answer,
      is_correct: result.is_correct,
      correct_answer: result.correct_answer,
      explanation: result.explanation,
      submitted_at: result.submitted_at
    }
    applyProgress(result.progress)
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
  }
}

const handlePrimary = async () => {
  if (!showResult.value) {
    await handleSubmit()
    return
  }

  if (isFinished.value && viewIndex.value >= progress.total - 1) {
    showSummary.value = true
    currentQuestion.value = null
    return
  }

  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    await loadQuestion(viewIndex.value + 1)
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const goPrev = async () => {
  if (viewIndex.value === 0) return
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    await loadQuestion(viewIndex.value - 1)
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const flattenKnowledge = (nodes: KnowledgeNode[], prefix: string) => {
  const result: { id: string; path: string; question_count: number }[] = []
  for (const node of nodes) {
    const path = prefix ? `${prefix} / ${node.name}` : node.name
    if (node.children && node.children.length > 0) {
      result.push(...flattenKnowledge(node.children, path))
    } else {
      result.push({ id: node.id, path, question_count: node.question_count })
    }
  }
  return result
}

const openPicker = async () => {
  showPicker.value = true
  if (subjects.value.length === 0) {
    try {
      subjects.value = await getSubjects()
    } catch (error) {
      console.error(error)
    }
  }
  pickerSubjectId.value = scope.subjectId || subjects.value[0]?.id || ''
  if (pickerSubjectId.value) {
    await selectPickerSubject(pickerSubjectId.value)
  }
  pickerKnowledgeId.value = scope.knowledgeId
}

const selectPickerSubject = async (subjectId: string) => {
  pickerSubjectId.value = subjectId
  pickerKnowledgeId.value = ''
  pickerLoading.value = true
  try {
    const tree = await getKnowledgeTree(subjectId)
    knowledgeOptions.value = flattenKnowledge(tree, '')
  } catch (error) {
    console.error(error)
  } finally {
    pickerLoading.value = false
  }
}

const confirmPicker = async () => {
  if (!pickerSubjectId.value) {
    showToast('请先选择学科')
    return
  }
  showPicker.value = false
  scope.subjectId = pickerSubjectId.value
  scope.knowledgeId = pickerKnowledgeId.value
  showSummary.value = false
  loading.value = true
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    await restoreOrStart()
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
    closeToast()
  }
}

const restart = async () => {
  showSummary.value = false
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    if (mode.value === 'error_practice') {
      await startErrorSession()
    } else {
      await startNew()
    }
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const handleBack = () => {
  if (showSummary.value || !currentQuestion.value) {
    goBackToSubject()
    return
  }
  showConfirmDialog({
    title: '确认退出',
    message: '练习进度已保存，下次可从中断处继续'
  })
    .then(() => {
      goBackToSubject()
    })
    .catch(() => {})
}

const goBackToSubject = () => {
  if (scope.subjectId) {
    router.push(`/knowledge/${scope.subjectId}`)
  } else if (query.value.subjectId) {
    router.push(`/knowledge/${query.value.subjectId}`)
  } else {
    router.push('/subjects')
  }
}

const goErrorBook = () => {
  router.push('/errors')
}

onMounted(() => {
  initPractice()
})
</script>

<style scoped>
.practice-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f3ff 0%, #f5f7fa 100%);
  padding-bottom: 80px;
}

.nav-progress {
  font-size: 14px;
  color: white;
  opacity: 0.9;
}

.nav-switch {
  font-size: 18px;
  color: white;
}

.progress-header {
  padding: 12px 16px;
  background: white;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.question-container {
  padding: 16px;
}

.question-header {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.question-type {
  padding: 4px 10px;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.question-content {
  font-size: 16px;
  line-height: 1.8;
  color: #1a1a2e;
  margin-bottom: 24px;
  white-space: pre-wrap;
}

.options-container {
  margin-bottom: 20px;
}

.option-item {
  display: flex;
  align-items: flex-start;
  padding: 14px 16px;
  background: white;
  border-radius: 12px;
  margin-bottom: 10px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
}

.option-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.option-item.correct {
  border-color: #22c55e;
  background: #f0fdf4;
}

.option-item.wrong {
  border-color: #ef4444;
  background: #fef2f2;
}

.option-key {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f1f5f9;
  color: #475569;
  text-align: center;
  line-height: 28px;
  font-weight: 600;
  margin-right: 12px;
  flex-shrink: 0;
}

.selected .option-key {
  background: #3b82f6;
  color: white;
}

.correct .option-key {
  background: #22c55e;
  color: white;
}

.wrong .option-key {
  background: #ef4444;
  color: white;
}

.option-content {
  flex: 1;
  font-size: 15px;
  color: #334155;
  line-height: 1.6;
}

.fill-blank-container {
  background: white;
  border-radius: 12px;
  padding: 16px;
}

.fill-input {
  font-size: 16px;
}

.result-badge {
  text-align: center;
  padding: 12px;
  border-radius: 10px;
  font-weight: 600;
  margin-top: 16px;
}

.result-badge.correct {
  background: #f0fdf4;
  color: #15803d;
}

.result-badge.wrong {
  background: #fef2f2;
  color: #b91c1c;
}

.fill-result {
  background: white;
  border-radius: 12px;
  padding: 16px;
}

.result-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.result-row:last-child {
  margin-bottom: 0;
}

.result-label {
  font-size: 14px;
  color: #64748b;
  margin-right: 8px;
}

.result-value {
  font-size: 15px;
  font-weight: 500;
}

.result-value.correct {
  color: #15803d;
}

.result-value.wrong {
  color: #b91c1c;
}

.explanation-box {
  background: #f0f9ff;
  border-radius: 12px;
  padding: 16px;
  margin-top: 16px;
  border-left: 4px solid #3b82f6;
}

.explanation-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d4ed8;
  margin-bottom: 8px;
}

.explanation-content {
  font-size: 14px;
  line-height: 1.6;
  color: #475569;
}

.finished-container {
  padding: 40px 20px;
  text-align: center;
}

.score-circle {
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: white;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.15);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
}

.score-value {
  font-size: 36px;
  font-weight: 700;
  color: #3b82f6;
}

.score-label {
  font-size: 13px;
  color: #64748b;
}

.finished-stats {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin-bottom: 16px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
}

.stat-value.correct {
  color: #22c55e;
}

.stat-value.wrong {
  color: #ef4444;
}

.stat-label {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

.archive-hint {
  font-size: 13px;
  color: #64748b;
  background: #fff7ed;
  border-radius: 10px;
  padding: 10px 16px;
  margin: 0 8px 8px;
}

.finished-actions {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-container {
  padding-top: 80px;
}

.nav-bottom {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: white;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
}

.nav-bottom .van-button {
  flex: 1;
}

.picker {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #f1f5f9;
}

.picker-title {
  font-size: 16px;
  font-weight: 600;
}

.picker-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.picker-label {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 12px;
  margin-top: 8px;
}

.subject-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.chip {
  padding: 8px 14px;
  border-radius: 20px;
  background: #f1f5f9;
  font-size: 13px;
  color: #334155;
  cursor: pointer;
}

.chip.active {
  background: #3b82f6;
  color: white;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.knowledge-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
}

.knowledge-option.active {
  border-color: #3b82f6;
  background: #eff6ff;
}

.knowledge-name {
  font-size: 14px;
  color: #1a1a2e;
  flex: 1;
}

.knowledge-count {
  font-size: 12px;
  color: #3b82f6;
  margin-left: 8px;
}

.empty-tip {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 20px 0;
}

.loading-container {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.picker-footer {
  padding: 16px;
  border-top: 1px solid #f1f5f9;
}
</style>
