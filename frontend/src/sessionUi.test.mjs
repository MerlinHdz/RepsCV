import assert from 'node:assert/strict'
import test from 'node:test'
import { endLabel, modeLabel, resultLabel, formatDuration } from './sessionUi.ts'

test('Normal requires Finish and Max Set offers End', () => {
  assert.equal(endLabel('normal'), 'Finish workout')
  assert.equal(endLabel('max_set'), 'End Max Set')
  assert.equal(modeLabel('max_set'), 'Max Set')
})

test('completed and interrupted results have distinct states', () => {
  assert.equal(resultLabel({ status: 'completed' }), 'Workout completed')
  assert.match(resultLabel({ status: 'interrupted' }), /no XP/)
  assert.equal(formatDuration(65000), '1:05')
  assert.equal(formatDuration(null), '—')
})
