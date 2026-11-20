import {
  createAction,
  createSlice,
  type PayloadAction,
} from '@reduxjs/toolkit'

export type Audience = 'applicant' | 'student'
export type MessageRole = 'user' | 'assistant'

export interface ChatSource {
  title: string
  url: string
  section?: string
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  sources?: ChatSource[]
  followUps?: string[]
}

interface AssistantState {
  sessionId: string
  audience: Audience
  messages: ChatMessage[]
  status: 'idle' | 'loading' | 'failed'
  error: string | null
}

const initialState: AssistantState = {
  sessionId: crypto.randomUUID(),
  audience: 'applicant',
  messages: [],
  status: 'idle',
  error: null,
}

export const requestAnswer = createAction<string>('assistant/requestAnswer')

const assistantSlice = createSlice({
  name: 'assistant',
  initialState,
  reducers: {
    setAudience(state, action: PayloadAction<Audience>) {
      state.audience = action.payload
    },
    startNewSession(state, action: PayloadAction<string>) {
      state.sessionId = action.payload
      state.messages = []
      state.status = 'idle'
      state.error = null
    },
    addUserMessage(state, action: PayloadAction<ChatMessage>) {
      state.messages.push(action.payload)
      state.status = 'loading'
      state.error = null
    },
    answerReceived(state, action: PayloadAction<ChatMessage>) {
      state.messages.push(action.payload)
      state.status = 'idle'
      state.error = null
    },
    requestFailed(state, action: PayloadAction<string>) {
      state.status = 'failed'
      state.error = action.payload
    },
  },
  extraReducers: (builder) => {
    builder.addCase(requestAnswer, (state) => {
      state.status = 'loading'
      state.error = null
    })
  },
})

export const assistantActions = assistantSlice.actions
export const assistantReducer = assistantSlice.reducer
