import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import PoseDetector from './PoseDetector'
import { api, type WorkoutResult } from './api'
import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision'

vi.mock('./api', () => ({ api: { start: vi.fn(), finish: vi.fn(), status: vi.fn() } }))
vi.mock('@mediapipe/tasks-vision', () => ({
  FilesetResolver: { forVisionTasks: vi.fn() },
  PoseLandmarker: { createFromOptions: vi.fn(), POSE_CONNECTIONS: [] },
  DrawingUtils: class { drawConnectors() {} drawLandmarks() {} },
}))

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

test('prepares camera before Start, submits Finish once, and releases media', async () => {
  const stop = vi.fn()
  const close = vi.fn()
  const stream = { getTracks: () => [{ stop }], getVideoTracks: () => [{ stop }] }
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue(stream) } })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect: vi.fn() } as never)
  vi.mocked(FilesetResolver.forVisionTasks).mockResolvedValue({} as never)
  vi.mocked(PoseLandmarker.createFromOptions).mockResolvedValue({
    detectForVideo: () => ({ landmarks: [Array.from({ length: 33 }, () => ({ x: 0, y: 0, visibility: 1 }))] }),
    close,
  } as never)
  let nextFrame: FrameRequestCallback | undefined
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => { nextFrame = callback; return 1 }))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  class MockWebSocket {
    static OPEN = 1
    readyState = 0
    bufferedAmount = 0
    onopen: (() => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: (() => void) | null = null
    onclose: (() => void) | null = null
    constructor() {}
    close() {}
    send() {}
  }
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.mocked(api.start).mockResolvedValue({ id: 7, mode: 'normal', status: 'active',
    rep_count: 0, started_at: new Date().toISOString(), remaining_ms: null })
  let resolveFinish!: (result: WorkoutResult) => void
  vi.mocked(api.finish).mockImplementation(() => new Promise((resolve) => { resolveFinish = resolve }))
  const onResult = vi.fn()
  const view = render(<PoseDetector mode="normal" csrfToken="csrf" onResult={onResult} onBack={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Prepare camera' }))
  const start = await screen.findByRole('button', { name: 'Start workout' })
  expect((start as HTMLButtonElement).disabled).toBe(true)
  const video = screen.getByLabelText('Live camera')
  Object.defineProperties(video, { readyState: { value: 2 }, videoWidth: { value: 640 }, videoHeight: { value: 480 } })
  act(() => nextFrame?.(100))
  expect((start as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(start)
  await screen.findByRole('button', { name: 'Finish workout' })
  expect(api.start).toHaveBeenCalledWith('normal', 'csrf')
  const finish = screen.getByRole('button', { name: 'Finish workout' })
  fireEvent.click(finish)
  fireEvent.click(finish)
  expect(api.finish).toHaveBeenCalledTimes(1)
  await act(async () => resolveFinish({ type: 'workout_result', session_id: 7,
    mode: 'normal', status: 'completed', rep_count: 0, duration_ms: 1000,
    xp_earned: 0, new_personal_best: false, completed_at: new Date().toISOString() }))
  await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1))
  view.unmount()
  expect(stop).toHaveBeenCalled()
  expect(close).toHaveBeenCalled()
})
