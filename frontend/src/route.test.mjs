import assert from 'node:assert/strict'
import test from 'node:test'
import { parseRoute, routeHash } from './route.ts'

test('known screens and result links round trip through the hash router', () => {
  for (const name of ['dashboard', 'workout', 'history', 'leaderboard', 'profile']) {
    assert.deepEqual(parseRoute(routeHash({ name })), { name })
  }
  assert.deepEqual(parseRoute('/history'), { name: 'history' })
  assert.deepEqual(parseRoute('/leaderboard'), { name: 'leaderboard' })
  assert.deepEqual(parseRoute('#/result/42'), { name: 'result', sessionId: 42 })
  assert.deepEqual(parseRoute('#/result/nope'), { name: 'dashboard' })
  assert.deepEqual(parseRoute('#/unknown'), { name: 'dashboard' })
})
