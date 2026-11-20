import axios from 'axios'
import type { EventChannel, SagaIterator } from 'redux-saga'
import { call, delay, put, race, select, take, takeLatest } from 'redux-saga/effects'
import {
  openChatSocket,
  recoverAnswer,
  sendAssistantMessage,
  type AcceptedRequest,
  type ChatSocketEvent,
} from '../../api/api'
import type { ChatMessage } from '../../api/messageBlocks'
import { assistantActions, requestAnswer } from '../assistantSlice'
import type { RootState } from '../store'

class ConnectionLost extends Error {
  constructor() {
    super('Не удалось связаться с помощником. Проверьте подключение и повторите попытку.')
  }
}

function* readReply(socket: EventChannel<ChatSocketEvent>, request: AcceptedRequest): SagaIterator<ChatMessage> {
  while (true) {
    const event: ChatSocketEvent = yield take(socket)
    if (event.type === 'disconnected') throw new ConnectionLost()
    if (event.type === 'answer' && event.chatId === request.chatId &&
      event.requestMessageId === request.messageId) return event.message
  }
}

function* answerWorker(action: ReturnType<typeof requestAnswer>): SagaIterator {
  if (!requestAnswer.match(action)) return

  const state: RootState['assistant'] = yield select((root: RootState) => root.assistant)
  const question = state.messages.at(-1)?.blocks[0]
  if (state.sessionId !== action.payload || question?.type !== 'text') return

  const userId = state.sessionId
  const controller = new AbortController()
  let request = state.chatId && state.pendingMessageId
    ? { chatId: state.chatId, messageId: state.pendingMessageId }
    : null

  try {
    // Once the backend accepted a question, retries recover its answer without posting it twice.
    for (let attempt = 0; ; attempt++) {
      const socket: EventChannel<ChatSocketEvent> = yield call(openChatSocket, userId)
      try {
        const { event }: { event?: ChatSocketEvent } = yield race({
          event: take(socket),
          timeout: delay(8_000),
        })
        if (event?.type !== 'ready') throw new ConnectionLost()

        if (request) {
          const answer: ChatMessage | undefined = yield call(recoverAnswer, userId, request, controller.signal)
          if (answer) {
            yield put(assistantActions.answerReceived(answer))
            return
          }
        } else {
          const accepted: AcceptedRequest = yield call(
            sendAssistantMessage, userId, state.chatId, question.message, controller.signal,
          )
          request = accepted
          yield put(assistantActions.requestAccepted(accepted))
        }

        const { answer }: { answer?: ChatMessage } = yield race({
          answer: call(readReply, socket, request),
          timeout: delay(210_000),
        })
        if (!answer) throw new Error('Помощник ещё не ответил. Нажмите «Повторить», чтобы проверить ответ.')

        yield put(assistantActions.answerReceived(answer))
        return
      } catch (error) {
        if (!(error instanceof ConnectionLost) || !request || attempt >= 2) throw error
      } finally {
        socket.close()
      }
      yield delay(500 * (attempt + 1))
    }
  } catch (error) {
    const message = error instanceof Error && !axios.isAxiosError(error)
      ? error.message
      : 'Не удалось обработать запрос. Проверьте подключение и повторите попытку.'
    yield put(assistantActions.requestFailed(message))
  } finally {
    controller.abort()
  }
}

export function* assistantSaga() {
  yield takeLatest([requestAnswer.type, assistantActions.startNewSession.type], answerWorker)
}
