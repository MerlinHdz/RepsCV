import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DrawingUtils,
  FilesetResolver,
  PoseLandmarker,
} from '@mediapipe/tasks-vision'
import { poseFrame } from './poseFrame'
import './App.css'

type EngineResponse = {
  reps: number
  state: 'UNKNOWN' | 'UP' | 'DOWN'
  tracking: 'tracked' | 'limited' | 'lost' | 'error'
  form_valid: boolean
  feedback: string
  elbow_angle: number | null
  body_angle: number | null
  error?: string
}

function socketUrl() {
  const configured = import.meta.env.VITE_WS_URL as string | undefined
  if (configured) return configured
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.hostname}:8000/ws`
}

export default function PoseDetector() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const modelRef = useRef<PoseLandmarker | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const frameRef = useRef<number | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionRef = useRef(0)
  const startingRef = useRef(false)
  const activeRef = useRef(false)
  const lastSentRef = useRef(0)
  const [active, setActive] = useState(false)
  const [starting, setStarting] = useState(false)
  const [status, setStatus] = useState('Camera is off')
  const [tracking, setTracking] = useState('Waiting for camera')
  const [feedback, setFeedback] = useState('Place the camera to your side, with your full body in view.')
  const [reps, setReps] = useState(0)
  const [phase, setPhase] = useState('UNKNOWN')
  const [formValid, setFormValid] = useState(false)

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
  }, [])

  useEffect(() => () => {
    sessionRef.current += 1
    activeRef.current = false
    releaseResources()
  }, [releaseResources])

  function stopSession() {
    sessionRef.current += 1
    activeRef.current = false
    startingRef.current = false
    setStarting(false)
    releaseResources()
    setActive(false)
    setStatus('Camera is off')
    setTracking('Waiting for camera')
    setFormValid(false)
    setPhase('UNKNOWN')
    setFeedback('Place the camera to your side, with your full body in view.')
  }

  async function startSession() {
    if (activeRef.current || startingRef.current) return
    startingRef.current = true
    setStarting(true)
    const session = ++sessionRef.current
    setStatus('Requesting camera…')
    setFeedback('Allow camera access to start tracking.')
    setReps(0)
    const current = () => sessionRef.current === session

    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable. Use HTTPS or localhost.')
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
      if (!current()) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      for (const track of stream.getVideoTracks()) {
        track.onended = () => {
          if (current()) {
            stopSession()
            setStatus('Camera disconnected')
            setFeedback('Reconnect your camera and start again.')
          }
        }
      }
      const video = videoRef.current
      if (!video) throw new Error('Video element is unavailable.')
      video.srcObject = stream
      await video.play()
      if (!current()) return

      setStatus('Loading pose model…')
      const vision = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.0/wasm',
      )
      if (!current()) return
      const model = await PoseLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
        },
        runningMode: 'VIDEO',
        numPoses: 1,
      })
      if (!current()) {
        model.close()
        return
      }
      modelRef.current = model
      activeRef.current = true
      setActive(true)
      setStatus('Connecting to Python…')

      let retries = 0
      const connect = () => {
        if (!current() || !activeRef.current) return
        let socket: WebSocket
        try {
          socket = new WebSocket(socketUrl())
        } catch {
          scheduleReconnect()
          return
        }
        socketRef.current = socket
        socket.onopen = () => {
          if (!current()) return
          retries = 0
          setReps(0) // Each Python WebSocket connection owns its own session.
          setPhase('UNKNOWN')
          setStatus('Connected to Python')
          setFeedback('Hold the top push-up position to begin.')
        }
        socket.onmessage = (event) => {
          if (!current()) return
          try {
            const data = JSON.parse(event.data) as EngineResponse
            if (typeof data.reps !== 'number' || typeof data.feedback !== 'string') throw new Error('Invalid response')
            setReps(data.reps)
            setPhase(data.state)
            setTracking(data.tracking)
            setFormValid(data.form_valid)
            setFeedback(data.feedback)
            if (!data.error) setStatus('Connected to Python')
          } catch {
            setStatus('Invalid response from Python')
          }
        }
        socket.onerror = () => {
          if (current()) setStatus('Python connection error')
        }
        socket.onclose = () => {
          if (socketRef.current === socket) socketRef.current = null
          if (current() && activeRef.current) {
            setStatus('Python disconnected; reconnecting…')
            setTracking('Connection lost')
            setFormValid(false)
            setFeedback('Reconnecting. The rep count will restart when connected.')
            scheduleReconnect()
          }
        }
      }
      const scheduleReconnect = () => {
        if (!current() || !activeRef.current || retryRef.current !== null) return
        const delay = Math.min(1000 * 2 ** retries, 8000)
        retries += 1
        retryRef.current = setTimeout(() => {
          retryRef.current = null
          connect()
        }, delay)
      }
      connect()

      const trackFrame = () => {
        if (!current() || !activeRef.current) return
        try {
          const video = videoRef.current
          const model = modelRef.current
          if (video && model && video.readyState >= 2 && video.videoHeight > 0) {
            const now = performance.now()
            const result = model.detectForVideo(video, now)
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
              socket.send(JSON.stringify(poseFrame(result.landmarks[0], video.videoWidth / video.videoHeight)))
              lastSentRef.current = now
            }
          }
        } catch (error) {
          console.error('Pose detection failed:', error)
          stopSession()
          setStatus('Pose model failed')
          setFeedback('Restart tracking. If this continues, reload the page.')
          return
        }
        frameRef.current = requestAnimationFrame(trackFrame)
      }
      frameRef.current = requestAnimationFrame(trackFrame)
    } catch (error) {
      if (current()) {
        console.error('Could not start tracking:', error)
        stopSession()
        const message = error instanceof Error ? error.message : 'Camera or model unavailable.'
        setStatus('Could not start tracking')
        setFeedback(message)
      }
    } finally {
      if (current()) {
        startingRef.current = false
        setStarting(false)
      }
    }
  }

  return (
    <main className="detector">
      <header>
        <p className="eyebrow">RepsCV · Push-up tracker</p>
        <h1>Every rep, in view.</h1>
        <p>Place your camera to the side and keep your full body visible.</p>
      </header>

      <section className="dashboard" aria-label="Live workout status">
        <div className="count-card"><span>Push-ups</span><strong aria-live="polite">{reps}</strong><small>Current connection</small></div>
        <div className="status-card">
          <p><span className="label">Session</span><strong>{status}</strong></p>
          <p><span className="label">Tracking</span><strong>{tracking}</strong></p>
          <p><span className="label">Movement</span><strong>{phase === 'UNKNOWN' ? 'Get ready' : phase === 'UP' ? 'At top' : 'At bottom'}</strong></p>
          <p><span className="label">Form</span><strong>{formValid ? 'Valid' : 'Needs attention'}</strong></p>
        </div>
      </section>

      <div className="camera-frame">
        <video ref={videoRef} autoPlay playsInline muted aria-label="Live camera" />
        <canvas ref={canvasRef} aria-hidden="true" />
        {!active && <span className="camera-placeholder">Camera preview</span>}
      </div>
      <p className="feedback" role="status" aria-live="polite">{feedback}</p>
      <div className="actions">
        <button type="button" onClick={startSession} disabled={active || starting}>{active ? 'Tracking' : starting ? 'Starting…' : 'Start tracking'}</button>
        <button type="button" className="secondary" onClick={stopSession} disabled={!active && !starting}>Stop</button>
      </div>
    </main>
  )
}
