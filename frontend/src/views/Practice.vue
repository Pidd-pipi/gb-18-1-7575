<template>
  <div class="practice-page">
    <van-nav-bar
      :title="modeName"
      left-arrow
      @click-left="handleBack"
    >
      <template #right>
        <span class="nav-progress">{{ Math.min(viewIndex + 1, progress.total) }} / {{ progress.total }}</span>
      </template>
    </van-nav-bar>

    <div class="progress-header">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-stats">
        <span>正确率 {{ progress.accuracy }}%</span>
        <span>已对 {{ progress.correct }} 题</span>
      </div>
    </div>

    <div class="question-container" v-if="currentQuestion && !showFinished">
      <div class="question-header">
        <span class="question-type">{{ questionTypeLabel }}</span>
        <span class="difficulty-tag" :class="'difficulty-' + currentQuestion.difficulty">
          {{ difficultyLabel }}
        </span>
        <span v-if="currentRecord" class="answered-tag">已作答</span>
      </div>

      <div class="question-content">
        {{ currentQuestion.content }}
      </div>

      <!-- 作答区：仅当前未完成题可作答 -->
      <div v-if="!currentRecord" class="options-container">
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

      <!-- 反馈区：正确答案、解析随提交一起保存并回读 -->
      <div v-else class="result-container">
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
              <span class="result-value" :class="currentRecord.is_correct ? 'correct' : 'wrong'">
                {{ currentRecord.user_answer || '未作答' }}
              </span>
            </div>
            <div class="result-row">
              <span class="result-label">正确答案：</span>
              <span class="result-value correct">{{ currentRecord.correct_answer }}</span>
            </div>
          </div>
        </div>

        <div class="result-badge" :class="currentRecord.is_correct ? 'correct' : 'wrong'">
          {{ currentRecord.is_correct ? '✓ 回答正确' : '✗ 回答错误' }}
        </div>

        <div v-if="currentRecord.explanation" class="explanation-box">
          <div class="explanation-title">解析</div>
          <div class="explanation-content">{{ currentRecord.explanation }}</div>
        </div>
      </div>
    </div>

    <!-- 完成页：本次正确率，错题已自动归档 -->
    <div v-if="showFinished" class="finished-container">
      <div class="score-circle">
        <div class="score-value">{{ finalAccuracy }}</div>
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
        错题已自动收入错题本，可前往错题重练
      </div>

      <div class="finished-actions">
        <van-button type="primary" block round @click="goHome">
          返回首页
        </van-button>
        <van-button block round @click="goBackToSubject">
          继续练习
        </van-button>
      </div>
    </div>

    <div class="nav-bottom" v-if="!showFinished && currentQuestion">
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
        :disabled="!currentRecord && !hasAnswer"
        @click="handlePrimary"
      >
        {{ primaryButtonText }}
      </van-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showLoadingToast, closeToast, showToast } from 'vant'
import { startPractice, submitAnswer, getQuestionAt } from '@/api/practice'
import type { Question, AnswerRecord, QuestionOption } from '@/types'

const route = useRoute()
const router = useRouter()

const mode = computed(() => route.params.mode as string)
const query = computed(() => route.query)

const sessionId = ref('')
const viewIndex = ref(0)
const currentQuestion = ref<Question | null>(null)
const answers = ref<Record<string, AnswerRecord>>({})
const selectedAnswer = ref<any>(null)
const selectedAnswers = ref<string[]>([])
const fillAnswer = ref('')
const showFinished = ref(false)
const sessionDone = ref(false)
const finalAccuracy = ref(0)
const submitting = ref(false)

const progress = reactive({
  current: 0,
  total: 0,
  correct: 0,
  accuracy: 0
})

const currentRecord = computed<AnswerRecord | null>(() => {
  const q = currentQuestion.value
  return q ? answers.value[q.id] ?? null : null
})

const modeName = computed(() => {
  const modeMap: Record<string, string> = {
    sequential: '顺序练习',
    random: '随机练习',
    error_practice: '错题重练'
  }
  return modeMap[mode.value] || '练习'
})

const progressPercent = computed(() => {
  if (!progress.total) return 0
  return Math.round((progress.current / progress.total) * 100)
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

// 判断题未配置选项时使用默认「正确/错误」
const displayOptions = computed<QuestionOption[]>(() => {
  const q = currentQuestion.value
  if (!q) return []
  if (q.type === 'true_false' && (!q.options || q.options.length === 0)) {
    return [
      { key: 'A', content: '正确' },
      { key: 'B', content: '错误' }
    ]
  }
  return q.options || []
})

const hasAnswer = computed(() => {
  const q = currentQuestion.value
  if (!q) return false
  if (q.type === 'fill_blank') return fillAnswer.value.trim().length > 0
  if (q.type === 'multiple_choice') return selectedAnswers.value.length > 0
  return selectedAnswer.value !== null && selectedAnswer.value !== undefined
})

const primaryButtonText = computed(() => {
  if (!currentRecord.value) return '提交答案'
  if (sessionDone.value && viewIndex.value >= progress.total - 1) return '查看结果'
  return '下一题'
})

const asList = (v: any): any[] => (Array.isArray(v) ? v : [v])

const isOptionSelected = (key: string) => {
  if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value.includes(key)
  }
  return selectedAnswer.value === key
}

const getOptionClass = (key: string) => {
  const record = currentRecord.value
  if (!record) return []
  const classes: string[] = []
  const correctKeys = asList(record.correct_answer).map(String)
  const userKeys = asList(record.user_answer).map(String)
  if (correctKeys.includes(key)) {
    classes.push('correct')
  } else if (userKeys.includes(key)) {
    classes.push('wrong')
  }
  return classes
}

const selectOption = (key: string) => {
  if (currentRecord.value) return

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

const applyProgress = (p: { current: number; total: number; correct: number; accuracy: number }) => {
  progress.current = p.current
  progress.total = p.total
  progress.correct = p.correct
  progress.accuracy = p.accuracy
}

const resetAnswerState = () => {
  selectedAnswer.value = null
  selectedAnswers.value = []
  fillAnswer.value = ''
}

const handlePrimary = async () => {
  if (!currentRecord.value) {
    await doSubmit()
  } else if (sessionDone.value && viewIndex.value >= progress.total - 1) {
    showFinished.value = true
  } else {
    await goNext()
  }
}

const doSubmit = async () => {
  if (!hasAnswer.value || !currentQuestion.value) return

  submitting.value = true
  try {
    const answer = getAnswerToSubmit()
    const result = await submitAnswer(sessionId.value, currentQuestion.value.id, answer)

    answers.value[currentQuestion.value.id] = {
      user_answer: answer,
      is_correct: result.is_correct,
      correct_answer: result.correct_answer,
      explanation: result.explanation
    }
    applyProgress(result.progress)

    if (result.is_finished) {
      sessionDone.value = true
      finalAccuracy.value = result.final_accuracy ?? result.progress.accuracy
    }
  } catch (error) {
    console.error(error)
  } finally {
    submitting.value = false
  }
}

const loadQuestionAt = async (index: number) => {
  const data = await getQuestionAt(sessionId.value, index)
  currentQuestion.value = data.question
  viewIndex.value = index
  applyProgress(data.progress)
  if (data.record) {
    answers.value[data.question.id] = data.record
  }
  resetAnswerState()
}

const goNext = async () => {
  if (viewIndex.value >= progress.total - 1) return
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    await loadQuestionAt(viewIndex.value + 1)
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
    await loadQuestionAt(viewIndex.value - 1)
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const handleBack = () => {
  showConfirmDialog({
    title: '确认退出',
    message: '练习进度已保存，下次可从中断处继续。确定要退出吗？'
  })
    .then(() => {
      goBackToSubject()
    })
    .catch(() => {})
}

const goBackToSubject = () => {
  if (query.value.subjectId) {
    router.push(`/knowledge/${query.value.subjectId}`)
  } else {
    router.push('/subjects')
  }
}

const goHome = () => {
  router.push('/')
}

const initPractice = async () => {
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    const knowledgeIds = query.value.knowledgeIds
      ? [query.value.knowledgeIds as string]
      : undefined

    const startResult = await startPractice({
      mode: mode.value,
      subject_id: (query.value.subjectId as string) || undefined,
      knowledge_ids: knowledgeIds,
      question_count: parseInt(query.value.count as string) || 20,
      difficulty: (query.value.difficulty as string) || undefined
    })

    sessionId.value = startResult.session_id
    answers.value = startResult.answers || {}
    applyProgress(startResult.progress)

    if (startResult.is_finished || !startResult.current_question) {
      // 会话已完成：直接展示本次正确率
      sessionDone.value = true
      finalAccuracy.value = startResult.final_accuracy ?? startResult.progress.accuracy
      showFinished.value = true
      return
    }

    // 从下一未完成题恢复
    viewIndex.value = startResult.progress.current
    currentQuestion.value = startResult.current_question
    resetAnswerState()
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
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

.answered-tag {
  padding: 4px 10px;
  background: #f0fdf4;
  color: #15803d;
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

.finished-stats {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin-top: 32px;
}

.finished-stats .stat-value.correct {
  color: #22c55e;
}

.finished-stats .stat-value.wrong {
  color: #ef4444;
}

.archive-hint {
  margin-top: 24px;
  font-size: 13px;
  color: #b45309;
  background: #fffbeb;
  border-radius: 10px;
  padding: 10px 16px;
  display: inline-block;
}

.finished-actions {
  margin-top: 40px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
