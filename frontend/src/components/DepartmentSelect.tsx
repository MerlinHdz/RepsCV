import type { DepartmentOption } from '../api'

type Props = {
  value: string
  onChange: (value: string) => void
  options: DepartmentOption[] | null
  loading: boolean
  error: string | null
  retry: () => void
  disabled?: boolean
}

export default function DepartmentSelect({ value, onChange, options, loading, error, retry, disabled }: Props) {
  const legacy = value && options && !options.some((option) => option.value === value)
  return <>
    <select id="department" value={value} onChange={(event) => onChange(event.target.value)}
      disabled={disabled || loading || Boolean(error)} aria-describedby={legacy || error ? 'department-help' : undefined}>
      <option value="">{loading ? 'Loading departments…' : 'Not specified'}</option>
      {value && (!options || legacy) && <option value={value} disabled>Previous entry: {value}</option>}
      {options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
    {legacy && !error && <p id="department-help">Your previous entry is preserved. Choose a department from the list or clear it.</p>}
    {error && <p id="department-help" role="alert">Could not load departments. <button type="button" className="button-ghost" onClick={retry} disabled={disabled}>Retry departments</button></p>}
  </>
}
