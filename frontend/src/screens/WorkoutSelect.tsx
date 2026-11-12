import type { Mode } from '../api'

type Props = { onSelect: (mode: Mode) => void; onBack: () => void }

export default function WorkoutSelect({ onSelect, onBack }: Props) {
  return (
    <div className="screen workout-select">
      <div className="screen-heading"><p className="eyebrow">Push-ups · Choose your session</p><h1>Pick your<br /><em>pace.</em></h1><p>Set your phone to the side so your full body stays in frame. The camera starts after you choose a mode.</p></div>
      <div className="mode-options">
        <button type="button" onClick={() => onSelect('normal')}>
          <span className="mode-number">01 / UNLIMITED REST</span><strong>Normal<br />Workout</strong><span>Move at your pace. Press Finish when you’re done.</span><span className="mode-arrow" aria-hidden="true">↗</span>
        </button>
        <button type="button" onClick={() => onSelect('max_set')}>
          <span className="mode-number">02 / TIMED SET</span><strong>Max<br />Set</strong><span>First rep in 20 seconds. Keep each next rep within 5.</span><span className="mode-arrow" aria-hidden="true">↗</span>
        </button>
      </div>
      <button type="button" className="text-action" onClick={onBack}>← Back to dashboard</button>
    </div>
  )
}
