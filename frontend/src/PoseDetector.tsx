import { useRef, useState } from "react";
import { calculateAngle } from "./utils/geometry";
import {
    FilesetResolver,
    PoseLandmarker,
    DrawingUtils
} from "@mediapipe/tasks-vision";

export default function PoseDetector() {
    const videoRef = useRef<HTMLVideoElement>(null);
    const landmarkerRef = useRef<PoseLandmarker | null>(null);
    const trackingRef = useRef(false);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [status, setStatus] = useState("Camera is off");

    async function startCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: false,
            });

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                setStatus("Camera is running!");
            }
        } catch (error) {
            console.error(error);
            setStatus("Could not access camera");
        }
    }


    async function loadPoseModel() {
        try {
            setStatus("Loading MediaPipe AI model...");

            const vision = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.32/wasm"
            );


            const landmarker = await PoseLandmarker.createFromOptions(vision, {
                baseOptions: {
                    modelAssetPath:
                        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
                },
                runningMode: "VIDEO",
                numPoses: 1,
            });

            landmarkerRef.current = landmarker;

            console.log("MediaPipe model loaded:", landmarker);
            setStatus("MediaPipe AI model ready!")
        } catch (error) {
            console.error("MediaPipe initialization failed:", error);
            setStatus("Failed to load MediaPipe model");
        }
    }

    function detectPose() {
        const video = videoRef.current;
        const landmarker = landmarkerRef.current;

        if (!video || !landmarker || video.readyState < 2) {
            setStatus("Start the camera and load the AI model first.");
            return;
        }

        const results = landmarker.detectForVideo(
            video,
            performance.now()
        );

        if (results.landmarks.length > 0) {
            console.log("Body landmarks:", results.landmarks[0]);
            setStatus(`Detected ${results.landmarks[0].length} body landmarks!`);
        } else {
            setStatus("No person detected. Stand in front of the camera.");
        }
    }


    function startTracking() {
        if (trackingRef.current) return;

        if (!videoRef.current || !landmarkerRef.current) {
            setStatus("Start the camera and load the AI model first.");
            return;
        }

        trackingRef.current = true;

        function trackFrame() {
            if (!trackingRef.current) return;

            const video = videoRef.current;
            const landmarker = landmarkerRef.current;

            if (video && landmarker && video.readyState >= 2) {
                const results = landmarker.detectForVideo(
                    video,
                    performance.now()
                );


                const canvas = canvasRef.current;

                if (canvas) {
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;

                    const ctx = canvas.getContext("2d");

                    if (ctx) {
                        ctx.clearRect(0, 0, canvas.width, canvas.height);

                        const drawingUtils = new DrawingUtils(ctx);

                        for (const landmarks of results.landmarks) {
                            drawingUtils.drawConnectors(
                                landmarks,
                                PoseLandmarker.POSE_CONNECTIONS,
                                { color: "#00FF88", lineWidth: 3 }
                            );

                            drawingUtils.drawLandmarks(landmarks, {
                                color: "#FF4444",
                                radius: 3,
                            });
                        }
                    }
                }


                if (results.landmarks.length > 0) {
                    const landmarks = results.landmarks[0];

                    const shoulder = landmarks[11];
                    const elbow = landmarks[13];
                    const wrist = landmarks[15];

                    const angle = calculateAngle(shoulder, elbow, wrist);

                    setStatus(`Left elbow angle: ${angle.toFixed(1)}°`);
                } else {
                    setStatus("Looking for a person...");
                }
            }

            requestAnimationFrame(trackFrame);
        }

        requestAnimationFrame(trackFrame);
    }



    return (
        <div>
            <h2>RepsCV Pose Detector</h2>

            <p>{status}</p>

            <div
                style={{
                    position: "relative",
                    width: "100%",
                    maxWidth: "640px",
                }}
            >
                <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    style={{ width: "100%", display: "block" }}
                />

                <canvas
                    ref={canvasRef}
                    style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: "100%",
                        pointerEvents: "none",
                    }}
                />
            </div>

            <button onClick={startCamera}>Start Camera</button>
            <button onClick={loadPoseModel}>Load AI Model</button>
            <button onClick={detectPose}>Detect Pose</button>
            <button onClick={startTracking}>Start Tracking</button>
        </div>
    );
}
