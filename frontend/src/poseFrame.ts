type Landmark = { x: number; y: number; visibility: number; presence?: number }

const LANDMARK_NAMES: Record<number, string> = {
  11: 'left_shoulder', 13: 'left_elbow', 15: 'left_wrist',
  23: 'left_hip', 27: 'left_ankle',
  12: 'right_shoulder', 14: 'right_elbow', 16: 'right_wrist',
  24: 'right_hip', 28: 'right_ankle',
}

export function poseFrame(landmarks: Landmark[] | undefined, aspectRatio: number) {
  if (!landmarks) return { aspect_ratio: aspectRatio, landmarks: null }
  const points: Record<string, Landmark & { presence: number }> = {}
  for (const [index, name] of Object.entries(LANDMARK_NAMES)) {
    const point = landmarks[Number(index)]
    if (point) {
      points[name] = {
        x: point.x, y: point.y,
        visibility: point.visibility,
        presence: point.presence ?? point.visibility,
      }
    }
  }
  return { aspect_ratio: aspectRatio, landmarks: points }
}
