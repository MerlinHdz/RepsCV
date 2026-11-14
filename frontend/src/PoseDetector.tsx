import { useCallback, useEffect, useRef, useState } from 'react'
import { DrawingUtils, FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision'
import { api, type ActiveWorkout, type Mode, type StartResponse, type WorkoutResult } from './api'
import { poseFrame } from './poseFrame'
import { endLabel, formatDuration, modeLabel } from './sessionUi'
import './App.css'

type Props = {
  mode: Mode
  csrfToken: string
  resume?: ActiveWorkout
  onResult: (result: WorkoutResult) => void
  onSessionStarted?: (session: ActiveWorkout) => void
  onBack: () => void
}

type Update = {
  type: string; rep_count?: number; phase?: string; tracking?: string
  form_valid?: boolean; feedback?: string; elapsed_ms?: number
  remaining_ms?: number | null
}

function workoutSocketUrl(id: number) {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}/ws/workouts/${id}`
}

export default function PoseDetector({ mode, csrfToken, resume, onResult, onSessionStarted, onBack }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const modelRef = useRef<PoseLandmarker | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const frameRef = useRef<number | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionGeneration = useRef(0)
  const cameraActive = useRef(false)
  const workoutIdRef = useRef<number | null>(resume?.id ?? null)
  const finishedRef = useRef(false)
  const workingRef = useRef(false)
  const sequenceRef = useRef(0)
  const lastSentRef = useRef(0)
  const deadlineViewRef = useRef<number | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [ready, setReady] = useState(false)
  const [connected, setConnected] = useState(false)
  const [poseSeen, setPoseSeen] = useState(false)
  const [session, setSession] = useState<ActiveWorkout | StartResponse | null>(resume ?? null)
  const [working, setWorking] = useState(false)
  const [status, setStatus] = useState(resume ? 'Prepare camera to resume' : 'Camera is off')
  const [tracking, setTracking] = useState('Waiting for camera')
  const [feedback, setFeedback] = useState('Place the camera to your side with your full body in view.')
  const [reps, setReps] = useState(resume?.rep_count ?? 0)
  const [phase, setPhase] = useState('UNKNOWN')
  const [formValid, setFormValid] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [remaining, setRemaining] = useState<number | null>(null)

  const releaseResources = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    if (retryRef.current !== null) clearTimeout(retryRef.current)
    retryRef.current = null
    const socket = socketRef.current
    socketRef.current = null
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
      socket.close()
    }
    modelRef.current?.close()
    modelRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    const canvas = canvasRef.current
    canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height)
    cameraActive.current = false
  }, [])

  useEffect(() => () => {
    sessionGeneration.current += 1
    releaseResources()
  }, [releaseResources])

  useEffect(() => {
    if (!session) return
    const interval = setInterval(() => {
      setElapsed(Math.max(0, Date.now() - Date.parse(session.started_at)))
      if (deadlineViewRef.current !== null) setRemaining(Math.max(0, deadlineViewRef.current - Date.now()))
    }, 100)
    return () => clearInterval(interval)
  }, [session])

  useEffect(() => {
    if (!resume || resume.mode !== 'max_set') return
    let cancelled = false
    const check = async () => {
      if (cancelled) return
      try {
        const current = await api.status(resume.id)
        if (cancelled) return
        if (current.status !== 'active') {
          finishedRef.current = true
          onResult(current as WorkoutResult)
        } else setTimeout(check, 500)
      } catch { if (!cancelled) setTimeout(check, 1000) }
    }
    check()
    return () => { cancelled = true }
  }, [resume, onResult])

  function showResult(result: WorkoutResult) {
    if (finishedRef.current) return
    finishedRef.current = true
    sessionStorage.removeItem('repscv_workout_id')
    onResult(result)
  }

  async function pollMaxSetResult(id: number) {
    const generation = sessionGeneration.current
    for (let attempt = 0; attempt < 10 && !finishedRef.current; attempt++) {
      if (generation !== sessionGeneration.current) return
      try {
        const current = await api.status(id)
        if (generation !== sessionGeneration.current) return
        if (current.status !== 'active') {
          showResult(current as WorkoutResult)
          return
        }
      } catch { /* Retry while the server finishes the disconnect. */ }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    if (generation === sessionGeneration.current && !finishedRef.current) setFeedback('Connection lost. Reload to check the Max Set result.')
  }

  function connectSocket(id: number) {
    if (finishedRef.current || socketRef.current) return
    let socket: WebSocket
    try { socket = new WebSocket(workoutSocketUrl(id)) }
    catch { setStatus('Could not connect to Python'); return }
    socketRef.current = socket
    socket.onopen = () => {
      setStatus('Connected to Python')
      setConnected(true)
      setTracking('Looking for pose')
      sequenceRef.current = 0
    }
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Update & WorkoutResult
        if (data.type === 'workout_result') {
          showResult(data)
          return
        }
        if (data.type === 'workout_update') {
          setReps(data.rep_count ?? 0)
          setPhase(data.phase ?? 'UNKNOWN')
          setTracking(data.tracking ?? 'Unknown')
          setFormValid(Boolean(data.form_valid))
          setFeedback(data.feedback ?? '')
          if (data.remaining_ms !== null && data.remaining_ms !== undefined) {
            deadlineViewRef.current = Date.now() + data.remaining_ms
            setRemaining(data.remaining_ms)
          }
        } else if (data.type === 'error') setFeedback(data.feedback ?? 'Invalid pose frame.')
      } catch { setFeedback('Invalid response from Python.') }
    }
    socket.onerror = () => setStatus('Python connection error')
    socket.onclose = (event) => {
      if (socketRef.current === socket) socketRef.current = null
      setConnected(false)
      if (finishedRef.current || workoutIdRef.current !== id) return
      setStatus('Disconnected')
      setTracking('Disconnected')
      setFormValid(false)
      if ([4401, 4403, 4404, 4409].includes(event.code)) {
        setFeedback('Session unavailable or expired. Reload and sign in to recover your workout.')
        return
      }
      if (mode === 'max_set') {
        setFeedback('Max Set interrupted by the connection loss.')
        void pollMaxSetResult(id)
      } else {
        setFeedback('Reconnecting to the same Normal Workout…')
        retryRef.current = setTimeout(() => {
          retryRef.current = null
          if (!finishedRef.current && workoutIdRef.current === id) connectSocket(id)
        }, 1000)
      }
    }
  }

  async function prepareCamera() {
    if (cameraActive.current || preparing) return
    const generation = ++sessionGeneration.current
    setPreparing(true)
    setStatus('Requesting camera…')
    const current = () => generation === sessionGeneration.current
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Use HTTPS or localhost for camera access.')
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return }
      streamRef.current = stream
      const video = videoRef.current
      if (!video) throw new Error('Camera preview unavailable.')
      video.srcObject = stream
      for (const track of stream.getVideoTracks()) {
        track.onended = () => {
          if (!current()) return
          const workoutId = workoutIdRef.current
          releaseResources()
          setStatus('Camera disconnected')
          setFeedback('Reconnect your camera. A Max Set will be interrupted.')
          setReady(false)
          setPoseSeen(false)
          setConnected(false)
          if (workoutId !== null && mode === 'max_set') void pollMaxSetResult(workoutId)
        }
      }
      await video.play()
      if (!current()) return
      setStatus('Loading pose model…')
      const vision = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
      if (!current()) return
      const model = await PoseLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: '/mediapipe/pose_landmarker_lite.task' },
        runningMode: 'VIDEO', numPoses: 1,
      })
      if (!current()) { model.close(); return }
      modelRef.current = model
      cameraActive.current = true
      setReady(true)
      setStatus('Camera ready')

      let lastInference = 0
      const trackFrame = () => {
        if (!current() || !cameraActive.current) return
        if (performance.now() - lastInference < 80) {
          frameRef.current = requestAnimationFrame(trackFrame)
          return
        }
        lastInference = performance.now()
        try {
          const video = videoRef.current
          if (video && video.readyState >= 2 && video.videoHeight > 0) {
            const now = performance.now()
            const result = model.detectForVideo(video, now)
            setPoseSeen(result.landmarks.length > 0)
            const canvas = canvasRef.current
            if (canvas) {
              if (canvas.width !== video.videoWidth) canvas.width = video.videoWidth
              if (canvas.height !== video.videoHeight) canvas.height = video.videoHeight
              const context = canvas.getContext('2d')
              if (context) {
                context.clearRect(0, 0, canvas.width, canvas.height)
                const drawing = new DrawingUtils(context)
                for (const landmarks of result.landmarks) {
                  drawing.drawConnectors(landmarks, PoseLandmarker.POSE_CONNECTIONS, { color: '#50e6ad', lineWidth: 3 })
                  drawing.drawLandmarks(landmarks, { color: '#ff956b', radius: 3 })
                }
              }
            }
            const socket = socketRef.current
            if (socket?.readyState === WebSocket.OPEN && socket.bufferedAmount === 0 && now - lastSentRef.current >= 80) {
              const pose = poseFrame(result.landmarks[0], video.videoWidth / video.videoHeight)
              socket.send(JSON.stringify({ type: 'landmarks', sequence: sequenceRef.current++,
                timestamp_ms: now, aspect_ratio: pose.aspect_ratio, points: pose.landmarks }))
              lastSentRef.current = now
            }
          }
        } catch (cause) {
          console.error('Pose detection failed:', cause)
          const workoutId = workoutIdRef.current
          releaseResources()
          setStatus('Pose model failed')
          setFeedback('Reload the page to restart camera tracking.')
          setReady(false)
          setPoseSeen(false)
          setConnected(false)
          if (workoutId !== null && mode === 'max_set') void pollMaxSetResult(workoutId)
          return
        }
        frameRef.current = requestAnimationFrame(trackFrame)
      }
      frameRef.current = requestAnimationFrame(trackFrame)
    } catch (cause) {
      if (current()) {
        releaseResources()
        setStatus('Camera or model unavailable')
        setFeedback(cause instanceof Error ? cause.message : 'Could not start camera.')
      }
    } finally { if (current()) setPreparing(false) }
  }

  async function startWorkout() {
    if (!ready || !poseSeen || workingRef.current || finishedRef.current) return
    const generation = sessionGeneration.current
    workingRef.current = true
    setWorking(true)
    try {
      let current = session
      if (!current) {
        current = await api.start(mode, csrfToken)
        onSessionStarted?.(current)
        sessionStorage.setItem('repscv_workout_id', String(current.id))
        if (generation !== sessionGeneration.current) return
        setSession(current)
        setReps(0)
        const remainingMs = (current as StartResponse).remaining_ms
        if (remainingMs !== null) {
          deadlineViewRef.current = Date.now() + remainingMs
          setRemaining(remainingMs)
        }
      }
      workoutIdRef.current = current.id
      connectSocket(current.id)
      setStatus('Connecting to Python…')
    } catch (cause) {
      setFeedback(cause instanceof Error ? cause.message : 'Could not start workout.')
    } finally { workingRef.current = false; setWorking(false) }
  }

  async function finishWorkout() {
    if (!session || workingRef.current || finishedRef.current) return
    workingRef.current = true
    setWorking(true)
    try { showResult(await api.finish(session.id, csrfToken)) }
    catch (cause) { setFeedback(cause instanceof Error ? cause.message : 'Could not finish workout. Try again.') }
    finally { workingRef.current = false; setWorking(false) }
  }

  return (
    <main className="detector">
      <header><p className="eyebrow">RepsCV · {modeLabel(mode)}</p><h1>Every rep, in view.</h1><p>Place your camera to the side and keep your full body visible.</p></header>
      <section className="dashboard" aria-label="Live workout status">
        <div className="count-card"><span>Valid push-ups</span><strong aria-live="polite">{reps}</strong><small>Server count</small></div>
        <div className="status-card">
          <p><span className="label">Session</span><strong>{status}</strong></p>
          <p><span className="label">Tracking</span><strong>{tracking}</strong></p>
          <p><span className="label">Movement</span><strong>{phase === 'UNKNOWN' ? 'Get ready' : phase === 'UP' ? 'At top' : 'At bottom'}</strong></p>
          <p><span className="label">Form</span><strong>{formValid ? 'Valid' : 'Needs attention'}</strong></p>
        </div>
      </section>
      {session && <div className="timers"><p>Elapsed <strong>{formatDuration(elapsed)}</strong></p>{mode === 'max_set' && <p className="countdown">Next rep <strong>{remaining === null ? '…' : (remaining / 1000).toFixed(1)}s</strong></p>}</div>}
      <div className="camera-frame"><video ref={videoRef} autoPlay playsInline muted aria-label="Live camera" /><canvas ref={canvasRef} aria-hidden="true" />{!ready && <span className="camera-placeholder">Camera preview</span>}</div>
      <p className="feedback" role="status" aria-live="polite">{feedback}</p>
      <div className="actions">
        {!ready && <button type="button" onClick={prepareCamera} disabled={preparing || resume?.mode === 'max_set'}>{preparing ? 'Preparing…' : 'Prepare camera'}</button>}
        {ready && !session && <button type="button" onClick={startWorkout} disabled={!poseSeen || working}>{working ? 'Starting…' : 'Start workout'}</button>}
        {ready && session && !connected && mode === 'normal' && <button type="button" onClick={startWorkout} disabled={!poseSeen || working}>Reconnect tracking</button>}
        {session && <button type="button" onClick={finishWorkout} disabled={working}>{working ? 'Finishing…' : endLabel(mode)}</button>}
        {!session && <button type="button" className="secondary" onClick={onBack}>Back</button>}
      </div>
    </main>
  )
}
