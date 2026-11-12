import { api, type LeaderboardEntry } from '../api'
import { taiwanWeekLabel } from '../format'
import { useResource } from '../useResource'

function LeaderRow({ entry }: { entry: LeaderboardEntry }) {
  return <li className={`leader-row ${entry.is_current_user ? 'is-you' : ''}`}>
    <span className={`rank-mark rank-${entry.rank <= 3 ? entry.rank : 'other'}`}>{entry.rank <= 3 ? `#${entry.rank}` : entry.rank}</span>
    <span className="leader-name"><strong>{entry.username}</strong>{entry.is_current_user && <small>You</small>}</span>
    <strong className="leader-xp">{entry.weekly_xp.toLocaleString()} <small>XP</small></strong>
  </li>
}

export default function Leaderboard() {
  const { data, loading, error, retry } = useResource(api.leaderboard)
  return (
    <div className="screen">
      <div className="screen-heading"><p className="eyebrow">Campus-wide effort</p><h1>The weekly<br /><em>standings.</em></h1><p>Every completed rep earns its place. Equal XP shares the same rank.</p></div>
      {loading && <div className="loading-card" role="status">Loading this week’s standings…</div>}
      {error && <div className="error-card" role="alert"><p>Could not load the leaderboard: {error}</p><button type="button" onClick={retry}>Try again</button></div>}
      {data && <>
        <div className="week-banner"><span>This week · Asia/Taipei</span><strong>{taiwanWeekLabel(data.week_start, data.week_end)}</strong><small>Resets Monday at 00:00 Taipei time</small></div>
        {data.entries.length === 0
          ? <div className="empty-card"><span aria-hidden="true">◇</span><strong>No rankings yet</strong><p>Completed workouts will appear here.</p></div>
          : <>
            <div className="your-rank"><span>Your position</span><strong>#{data.current_user_rank ?? '—'}</strong><small>this week</small></div>
            <div className="section-heading"><div><p className="eyebrow">Earned, never given</p><h2>Global leaderboard</h2></div></div>
            <ol className="leader-list">{data.entries.map((entry) => <LeaderRow key={entry.user_id} entry={entry} />)}</ol>
          </>}
      </>}
    </div>
  )
}
