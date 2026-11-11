import assert from 'node:assert/strict'
import test from 'node:test'
import { poseFrame } from './poseFrame.ts'

test('serializes only the landmarks needed by Python and preserves confidence', () => {
  const landmarks = Array.from({ length: 33 }, () => ({ x: 0, y: 0, visibility: 0.1 }))
  landmarks[11] = { x: 0.2, y: 0.4, visibility: 0.9, presence: 0.8 }
  const result = poseFrame(landmarks, 16 / 9)
  assert.equal(result.aspect_ratio, 16 / 9)
  assert.equal(Object.keys(result.landmarks).length, 10)
  assert.deepEqual(result.landmarks.left_shoulder, { x: 0.2, y: 0.4, visibility: 0.9, presence: 0.8 })
  assert.equal(result.landmarks.right_shoulder.presence, 0.1)
})

test('reports missing pose explicitly', () => {
  assert.deepEqual(poseFrame(undefined, 4 / 3), { aspect_ratio: 4 / 3, landmarks: null })
})
