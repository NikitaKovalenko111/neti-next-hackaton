import {
  createAction,
  createSlice,
  type PayloadAction,
} from '@reduxjs/toolkit'
import type { AcceptedRequest } from '../api/api'
import type { Account } from '../api/account'
import type { ChatMessage } from '../api/messageBlocks'

interface AssistantState {
  account: Account | null
  sessionId: string
  chatId: string | null
  pendingMessageId: string | null
  messages: ChatMessage[]
  status: 'idle' | 'loading' | 'failed'
  error: string | null
}

const initialState: AssistantState = {
  account: null,
  sessionId: crypto.randomUUID(),
  chatId: null,
  pendingMessageId: null,
  messages: [],
  status: 'idle',
  error: null,
}

export const requestAnswer = createAction<string>('assistant/requestAnswer')

const assistantSlice = createSlice({
  name: 'assistant',
  initialState,
  reducers: {
    accountChanged(state, action: PayloadAction<{ account: Account | null; sessionId: string }>) {
      if (state.account?.id === action.payload.account?.id) return
      return { ...initialState, ...action.payload }
    },
    restoreChat(state, action: PayloadAction<{ accountId: string; sessionId: string; chatId: string; messages: ChatMessage[] }>) {
      if (state.account?.id !== action.payload.accountId) return
      state.sessionId = action.payload.sessionId
      state.chatId = action.payload.chatId
      state.messages = action.payload.messages
      const last = state.messages.at(-1)
      state.pendingMessageId = last?.role === 'user' ? last.id : null
      state.status = 'idle'
      state.error = null
    },
    startNewSession(state, action: PayloadAction<string>) {
      state.sessionId = action.payload
      state.chatId = null
      state.pendingMessageId = null
      state.messages = []
      state.status = 'idle'
      state.error = null
    },
    addUserMessage(state, action: PayloadAction<ChatMessage>) {
      state.messages.push(action.payload)
      state.status = 'loading'
      state.error = null
    },
    requestAccepted(state, action: PayloadAction<AcceptedRequest>) {
      state.chatId = action.payload.chatId
      state.pendingMessageId = action.payload.messageId
    },
    answerReceived(state, action: PayloadAction<ChatMessage>) {
      if (!state.messages.some((message) => message.id === action.payload.id)) {
        state.messages.push(action.payload)
      }
      state.pendingMessageId = null
      state.status = 'idle'
      state.error = null
    },
    requestFailed(state, action: PayloadAction<string>) {
      state.status = 'failed'
      state.error = action.payload
    },
  },
  extraReducers: (builder) => {
    builder.addCase(requestAnswer, (state, action) => {
      if (state.sessionId !== action.payload || state.messages.at(-1)?.role !== 'user') return
      state.status = 'loading'
      state.error = null
    })
  },
})

export const assistantActions = assistantSlice.actions
export const assistantReducer = assistantSlice.reducer
