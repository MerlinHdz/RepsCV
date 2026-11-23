import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import PoseDetector from './PoseDetector'
import { api, type Mode, type WorkoutResult } from './api'
import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision'

vi.mock('./api', () => ({ api: { start: vi.fn(), finish: vi.fn(), status: vi.fn() } }))
vi.mock('@mediapipe/tasks-vision', () => ({
  FilesetResolver: { forVisionTasks: vi.fn() },
  PoseLandmarker: { createFromOptions: vi.fn(), POSE_CONNECTIONS: [] },
  DrawingUtils: class { drawConnectors() {} drawLandmarks() {} },
}))

beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear() })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function cameraHarness(mode: Mode = 'normal') {
  vi.spyOn(performance, 'now').mockReturnValue(1000)
  const stop = vi.fn()
  const close = vi.fn()
  const stream = { getTracks: () => [{ stop }], getVideoTracks: () => [{ stop }] }
  const getUserMedia = vi.fn().mockResolvedValue(stream)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect: vi.fn() } as never)
  vi.mocked(FilesetResolver.forVisionTasks).mockResolvedValue({} as never)
  const detectForVideo = vi.fn(() => ({ landmarks: [Array.from({ length: 33 }, () => ({ x: 0, y: 0, visibility: 1 }))] }))
  vi.mocked(PoseLandmarker.createFromOptions).mockResolvedValue({
    detectForVideo,
    close,
  } as never)
  let nextFrame: FrameRequestCallback | undefined
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => { nextFrame = callback; return 1 }))
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  const sockets: MockWebSocket[] = []
  class MockWebSocket {
    static OPEN = 1
    readyState = 0
    bufferedAmount = 0
    onopen: (() => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: (() => void) | null = null
    onclose: ((event: CloseEvent) => void) | null = null
    constructor() { sockets.push(this) }
    close = vi.fn()
    send = vi.fn()
    open() { this.readyState = 1; this.onopen?.() }
    update(data: object) { this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent) }
  }
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.mocked(api.start).mockResolvedValue({ id: 7, mode, status: 'active',
    rep_count: 0, started_at: new Date().toISOString(), remaining_ms: mode === 'max_set' ? 20000 : null })
  async function prepare() {
    fireEvent.click(screen.getByRole('button', { name: 'Prepare camera' }))
    await screen.findAllByText('Camera ready')
    const video = screen.getByLabelText('Live camera')
    Object.defineProperties(video, { readyState: { value: 2 }, videoWidth: { value: 640 }, videoHeight: { value: 480 } })
    act(() => nextFrame?.(100))
  }
  function advanceFrame(now: number, videoTime: number) {
    vi.mocked(performance.now).mockReturnValue(now)
    const video = screen.getByLabelText('Live camera') as HTMLVideoElement
    video.currentTime = videoTime
    act(() => nextFrame?.(now))
  }
  return { stop, close, getUserMedia, sockets, prepare, detectForVideo, advanceFrame }
}

test('counter, feedback, and Finish stay in one console; Finish submits once and media is released', async () => {
  const camera = cameraHarness()
  let resolveFinish!: (result: WorkoutResult) => void
  vi.mocked(api.finish).mockImplementation(() => new Promise((resolve) => { resolveFinish = resolve }))
  const onResult = vi.fn()
  const view = render(<PoseDetector mode="normal" csrfToken="csrf" onResult={onResult} onBack={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Prepare camera' }))
  const start = await screen.findByRole('button', { name: 'Start workout' })
  expect((start as HTMLButtonElement).disabled).toBe(true)
  const video = screen.getByLabelText('Live camera')
  Object.defineProperties(video, { readyState: { value: 2 }, videoWidth: { value: 640 }, videoHeight: { value: 480 } })
  act(() => { vi.mocked(requestAnimationFrame).mock.calls.at(-1)?.[0](100) })
  expect((start as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(start)
  await screen.findByRole('button', { name: 'Finish workout' })
  expect(api.start).toHaveBeenCalledWith('normal', 'csrf')
  act(() => {
    camera.sockets[0].open()
    camera.sockets[0].update({ type: 'workout_update', rep_count: 4, phase: 'UP', tracking: 'tracked',
      form_valid: true, feedback: 'Good position. Lower your chest, then press up.',
      elbow_angle: 165, body_angle: 178, measured_side: 'left' })
  })
  expect(screen.getByText('left')).toBeTruthy()
  expect(screen.getByText('165° / 178°')).toBeTruthy()
  const consoleView = within(document.querySelector('.workout-console') as HTMLElement)
  expect(consoleView.getByText('4')).toBeTruthy()
  expect(consoleView.getByRole('status').textContent).toContain('Lower your chest')
  const finish = consoleView.getByRole('button', { name: 'Finish workout' })
  fireEvent.click(finish)
  fireEvent.click(finish)
  expect(api.finish).toHaveBeenCalledTimes(1)
  await act(async () => resolveFinish({ type: 'workout_result', session_id: 7,
    mode: 'normal', status: 'completed', rep_count: 4, duration_ms: 1000,
    xp_earned: 40, new_personal_best: false, completed_at: new Date().toISOString() }))
  await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1))
  view.unmount()
  expect(camera.stop).toHaveBeenCalled()
  expect(camera.close).toHaveBeenCalled()
  expect(camera.sockets[0].close).toHaveBeenCalled()
})

test('Max Set shows first/next rep countdown beside the accepted count and End control', async () => {
  const camera = cameraHarness('max_set')
  vi.mocked(api.finish).mockResolvedValue({ type: 'workout_result', session_id: 7,
    mode: 'max_set', status: 'completed', rep_count: 12, duration_ms: 30000,
    xp_earned: 120, new_personal_best: true, completed_at: new Date().toISOString() })
  const onResult = vi.fn()
  render(<PoseDetector mode="max_set" csrfToken="csrf" onResult={onResult} onBack={vi.fn()} />)
  await camera.prepare()
  fireEvent.click(screen.getByRole('button', { name: 'Start workout' }))
  await screen.findByText('20.0s')
  expect(screen.getByText('First rep in')).toBeTruthy()
  act(() => {
    camera.sockets[0].open()
    camera.sockets[0].update({ type: 'workout_update', rep_count: 12, remaining_ms: 5000,
      phase: 'UP', tracking: 'tracked', form_valid: true, feedback: 'Good position.' })
  })
  const metrics = within(screen.getByRole('region', { name: 'Live workout status' }))
  expect(metrics.getByText('12')).toBeTruthy()
  expect(metrics.getByText('Next rep in')).toBeTruthy()
  expect(metrics.getByText('5.0s')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'End Max Set' }))
  await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1))
  expect(api.finish).toHaveBeenCalledWith(7, 'csrf')
})

test('resumed Normal Workout keeps saved reps and reconnects without starting a new session', async () => {
  const camera = cameraHarness()
  render(<PoseDetector mode="normal" csrfToken="csrf" onResult={vi.fn()} onBack={vi.fn()}
    resume={{ id: 9, mode: 'normal', rep_count: 8, status: 'active', started_at: new Date().toISOString() }} />)
  expect(screen.getByText('8')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Finish workout' })).toBeTruthy()
  await camera.prepare()
  fireEvent.click(screen.getByRole('button', { name: 'Reconnect tracking' }))
  await waitFor(() => expect(camera.sockets).toHaveLength(1))
  expect(api.start).not.toHaveBeenCalled()
  expect(screen.getByText('8')).toBeTruthy()
})

test('camera denial keeps retry and Back available and never starts a workout', async () => {
  const camera = cameraHarness()
  camera.getUserMedia.mockRejectedValue(new Error('Camera permission denied. Allow access in browser settings.'))
  const back = vi.fn()
  render(<PoseDetector mode="normal" csrfToken="csrf" onResult={vi.fn()} onBack={back} />)
  fireEvent.click(screen.getByRole('button', { name: 'Prepare camera' }))
  await screen.findByText('Camera permission denied. Allow access in browser settings.')
  expect((screen.getByRole('button', { name: 'Prepare camera' }) as HTMLButtonElement).disabled).toBe(false)
  expect(api.start).not.toHaveBeenCalled()
  expect(camera.sockets).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(back).toHaveBeenCalledOnce()
})

test('frozen video cannot send repeated pose evidence; fresh frames resume without queued sends', async () => {
  const camera = cameraHarness()
  render(<PoseDetector mode="normal" csrfToken="csrf" onResult={vi.fn()} onBack={vi.fn()} />)
  await camera.prepare()
  fireEvent.click(screen.getByRole('button', { name: 'Start workout' }))
  await screen.findByRole('button', { name: 'Finish workout' })
  act(() => camera.sockets[0].open())
  camera.advanceFrame(1100, 0.1)
  expect(camera.sockets[0].send).toHaveBeenCalledTimes(1)
  camera.advanceFrame(1200, 0.1)
  camera.advanceFrame(1300, 0.1)
  expect(camera.sockets[0].send).toHaveBeenCalledTimes(1)
  expect(camera.detectForVideo).toHaveBeenCalledTimes(2) // Preview, then first new frame.
  camera.sockets[0].bufferedAmount = 100
  camera.advanceFrame(1400, 0.2)
  expect(camera.sockets[0].send).toHaveBeenCalledTimes(1)
  camera.sockets[0].bufferedAmount = 0
  camera.advanceFrame(1500, 0.3)
  expect(camera.sockets[0].send).toHaveBeenCalledTimes(2)
  const message = JSON.parse(camera.sockets[0].send.mock.calls[1][0])
  expect(message.sequence).toBe(1)
  expect(message.timestamp_ms).toBe(1500)
})
