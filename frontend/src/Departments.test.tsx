import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Auth from './screens/Auth'
import Profile from './screens/Profile'
import { api } from './api'

vi.mock('./api', () => ({ api: {
  departments: vi.fn(), register: vi.fn(), login: vi.fn(), me: vi.fn(), profile: vi.fn(),
} }))
const options = [
  { value: 'CS', label: 'CS — Computer Science' },
  { value: 'EE', label: 'EE — Electrical Engineering' },
]
const user = { id: 1, username: 'student', department: 'CS', csrf_token: 'csrf' }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.departments).mockResolvedValue(options)
  vi.mocked(api.me).mockResolvedValue(user)
})
afterEach(cleanup)

function profile(department: string | null = 'CS') {
  const onUpdate = vi.fn()
  render(<Profile user={{ ...user, department }} onUpdate={onUpdate} onLogout={vi.fn()} />)
  return onUpdate
}

test('registration selects a canonical code and keeps department optional', async () => {
  const authenticated = vi.fn()
  render(<Auth onAuthenticated={authenticated} />)
  fireEvent.click(screen.getByText(/New to RepsCV/))
  await screen.findByRole('option', { name: 'CS — Computer Science' })
  const select = screen.getByRole('combobox') as HTMLSelectElement
  expect(select.value).toBe('')
  fireEvent.change(select, { target: { value: 'EE' } })
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'student' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
  fireEvent.click(screen.getByRole('button', { name: /Create account/ }))
  await waitFor(() => expect(authenticated).toHaveBeenCalledWith(user))
  expect(api.register).toHaveBeenCalledWith('student', 'password123', 'EE')
  expect(screen.queryByPlaceholderText('e.g. Computer Science')).toBeNull()
})

test('profile loads existing code, saves selection, and clears to the optional value', async () => {
  const onUpdate = profile()
  await screen.findByRole('option', { name: 'EE — Electrical Engineering' })
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('CS')
  vi.mocked(api.profile).mockResolvedValue({ ...user, department: 'EE' })
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'EE' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save department' }))
  await screen.findByText('Department saved.')
  expect(api.profile).toHaveBeenCalledWith('EE', 'csrf')
  expect(onUpdate).toHaveBeenCalledWith({ ...user, department: 'EE' })
  vi.mocked(api.profile).mockResolvedValue({ ...user, department: null })
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  await screen.findByText('Department cleared.')
  expect(api.profile).toHaveBeenLastCalledWith('', 'csrf')
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('')
})

test('unrecognized legacy text stays visible and cannot be silently saved or cleared', async () => {
  const onUpdate = profile('Old program spelling')
  await screen.findByText(/Your previous entry is preserved/)
  expect(screen.getByText('Old program spelling')).toBeTruthy()
  const select = screen.getByRole('combobox') as HTMLSelectElement
  expect(select.value).toBe('Old program spelling')
  expect((screen.getByRole('button', { name: 'Save department' }) as HTMLButtonElement).disabled).toBe(true)
  expect(api.profile).not.toHaveBeenCalled()
  expect(onUpdate).not.toHaveBeenCalled()
  vi.mocked(api.profile).mockResolvedValue({ ...user, department: 'CS' })
  fireEvent.change(select, { target: { value: 'CS' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save department' }))
  await screen.findByText('Department saved.')
  expect(api.profile).toHaveBeenCalledWith('CS', 'csrf')
})

test('catalog failure offers retry without losing an existing department', async () => {
  vi.mocked(api.departments).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(options)
  profile()
  await screen.findByRole('alert')
  expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(true)
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('CS')
  fireEvent.click(screen.getByRole('button', { name: 'Retry departments' }))
  await screen.findByRole('option', { name: 'CS — Computer Science' })
  expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(false)
  expect(api.profile).not.toHaveBeenCalled()
})

test('failed profile update reports error and keeps persisted profile untouched', async () => {
  const onUpdate = profile()
  await screen.findByRole('option', { name: 'EE — Electrical Engineering' })
  vi.mocked(api.profile).mockRejectedValue(new Error('Storage unavailable.'))
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'EE' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save department' }))
  await screen.findByText('Storage unavailable.')
  expect(onUpdate).not.toHaveBeenCalled()
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('EE')
})
