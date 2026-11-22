import { configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { assistantReducer } from './assistantSlice'
import { assistantSaga } from './saga/saga'

const sagaMiddleware = createSagaMiddleware()

export const store = configureStore({
  reducer: {
    assistant: assistantReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(sagaMiddleware),
})

sagaMiddleware.run(assistantSaga)

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
