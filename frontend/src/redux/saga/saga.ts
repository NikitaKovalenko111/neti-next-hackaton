import axios from 'axios'
import { call, put, select, takeLatest } from 'redux-saga/effects'
import {
  sendAssistantMessage,
  type ChatResponse,
} from '../../api/api'
import { assistantActions, requestAnswer } from '../assistantSlice'
import type { RootState } from '../store'

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError<{ message?: string }>(error)) {
    return (
      error.response?.data?.message ??
      'Не удалось связаться с помощником. Проверьте подключение и повторите попытку.'
    )
  }

  return 'Произошла ошибка при подготовке ответа. Попробуйте ещё раз.'
}

function* answerWorker(action: ReturnType<typeof requestAnswer>) {
  try {
    const assistantState: RootState['assistant'] = yield select(
      (state: RootState) => state.assistant,
    )
    if (assistantState.sessionId !== action.payload) return

    const { sessionId, audience, messages } = assistantState
    const response: ChatResponse = yield call(sendAssistantMessage, {
      sessionId,
      audience,
      history: messages.map(({ role, content }) => ({ role, content })),
    })

    const activeSessionId: string = yield select(
      (state: RootState) => state.assistant.sessionId,
    )
    if (activeSessionId !== action.payload) return

    yield put(
      assistantActions.answerReceived({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        followUps: response.followUps,
      }),
    )
  } catch (error: unknown) {
    const activeSessionId: string = yield select(
      (state: RootState) => state.assistant.sessionId,
    )
    if (activeSessionId !== action.payload) return

    yield put(assistantActions.requestFailed(getErrorMessage(error)))
  }
}

export function* assistantSaga() {
  yield takeLatest(requestAnswer, answerWorker)
}
