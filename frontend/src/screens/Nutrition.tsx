import { useEffect, useState, type FormEvent } from 'react'
import { api, type NutritionInput } from '../api'
import { useResource } from '../useResource'

type Props = {
  csrfToken: string
}

export default function Nutrition({ csrfToken }: Props) {
  const { data, loading, error, retry } = useResource(api.nutrition)
  const {data: goals,loading: goalsLoading,retry: retryGoals,} = useResource(api.nutritionGoals)
  const {data: summary,loading: summaryLoading,error: summaryError,retry: retrySummary,} = useResource(api.nutritionSummary)
  const [mealType, setMealType] = useState('Breakfast')
  const [description, setDescription] = useState('')
  const [calories, setCalories] = useState('')
  const [protein, setProtein] = useState('')
  const [carbs, setCarbs] = useState('')
  const [fat, setFat] = useState('')
  const [water, setWater] = useState('')
  const [goalCalories, setGoalCalories] = useState('2200')
  const [goalProtein, setGoalProtein] = useState('120')
  const [goalCarbs, setGoalCarbs] = useState('250')
  const [goalFat, setGoalFat] = useState('70')
  const [goalWater, setGoalWater] = useState('2000')

  const [savingGoals, setSavingGoals] = useState(false)
  const [goalSaveError, setGoalSaveError] = useState<string | null>(null)
  const [goalSaveSuccess, setGoalSaveSuccess] = useState(false)
    useEffect(() => {
    if (!goals) return

    setGoalCalories(String(goals.calories))
    setGoalProtein(String(goals.protein))
    setGoalCarbs(String(goals.carbs))
    setGoalFat(String(goals.fat))
    setGoalWater(String(goals.water_ml))
  }, [goals])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  function optionalNumber(value: string): number | null {
    return value.trim() === '' ? null : Number(value)
  }
  async function handleGoalsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSavingGoals(true)
    setGoalSaveError(null)
    setGoalSaveSuccess(false)

    try {
      await api.updateNutritionGoals(
        {
          calories: Number(goalCalories),
          protein: Number(goalProtein),
          carbs: Number(goalCarbs),
          fat: Number(goalFat),
          water_ml: Number(goalWater),
        },
        csrfToken
      )

      retryGoals()
      setGoalSaveSuccess(true)
    } catch (cause) {
      setGoalSaveError(
        cause instanceof Error ? cause.message : 'Could not save goals.'
      )
    } finally {
      setSavingGoals(false)
    }
  }
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setSaveError(null)

    const entry: NutritionInput = {
      meal_type: mealType,
      description: description.trim(),
      calories: optionalNumber(calories),
      protein: optionalNumber(protein),
      carbs: optionalNumber(carbs),
      fat: optionalNumber(fat),
      water_ml: optionalNumber(water),
    }

    try {
      await api.createNutrition(entry, csrfToken)

      setDescription('')
      setCalories('')
      setProtein('')
      setCarbs('')
      setFat('')
      setWater('')

      retry()
      retrySummary()
    } catch (cause) {
      setSaveError(
        cause instanceof Error ? cause.message : 'Could not save meal.'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="screen">
      <div className="screen-heading">
        <p className="eyebrow">Fuel your progress</p>
        <h1>Nutrition<br /><em>tracker.</em></h1>
        <p>Record your meals, calories and nutrients alongside your workouts.</p>
      </div>
      <div className="section-heading">
        <h2>Today's summary</h2>
      </div>

      {summaryLoading && (
        <div className="loading-card" role="status">
          Loading daily summary...
        </div>
      )}

      {summaryError && (
        <div className="error-card" role="alert">
          <p>Could not load daily summary: {summaryError}</p>
          <button type="button" onClick={retrySummary}>
            Try again
          </button>
        </div>
      )}

            {summary && goals && !summaryLoading && !goalsLoading && (
        <div className="workout-list">
          {[
            {
              name: 'Calories',
              current: summary.calories,
              target: goals.calories,
              unit: 'kcal',
            },
            {
              name: 'Protein',
              current: summary.protein,
              target: goals.protein,
              unit: 'g',
            },
            {
              name: 'Carbohydrates',
              current: summary.carbs,
              target: goals.carbs,
              unit: 'g',
            },
            {
              name: 'Fat',
              current: summary.fat,
              target: goals.fat,
              unit: 'g',
            },
            {
              name: 'Water',
              current: summary.water_ml,
              target: goals.water_ml,
              unit: 'ml',
            },
          ].map((item) => {
            const percentage =
              item.target > 0
                ? Math.min((item.current / item.target) * 100, 100)
                : 0

            return (
              <article className="workout-item" key={item.name}>
                <div className="workout-item-main">
                  <strong>{item.name}</strong>
                  <small>
                    {item.current} / {item.target} {item.unit}
                  </small>
                  <div
                    role="progressbar"
                    aria-label={`${item.name} daily goal`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(percentage)}
                    style={{
                      height: '8px',
                      background: '#e5e5e5',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      marginTop: '8px',
                    }}
                  >
                    <div
                      style={{
                        width: `${percentage}%`,
                        height: '100%',
                        background: '#6c9b76',
                        borderRadius: '8px',
                      }}
                    />
                  </div>
                </div>

                <div className="workout-item-numbers">
                  <strong>{Math.round(percentage)}%</strong>
                  <small>of goal</small>
                </div>
              </article>
            )
          })}
        </div>
      )}
            <form className="form-card" onSubmit={handleGoalsSubmit}>
        <h2>Daily nutrition goals</h2>
        <p>Set your daily targets for calories and nutrients.</p>

        <label htmlFor="goal-calories">Calories (kcal)</label>
        <input
          id="goal-calories"
          type="number"
          min="0"
          step="any"
          value={goalCalories}
          onChange={(event) => setGoalCalories(event.target.value)}
          required
        />

        <label htmlFor="goal-protein">Protein (g)</label>
        <input
          id="goal-protein"
          type="number"
          min="0"
          step="any"
          value={goalProtein}
          onChange={(event) => setGoalProtein(event.target.value)}
          required
        />

        <label htmlFor="goal-carbs">Carbohydrates (g)</label>
        <input
          id="goal-carbs"
          type="number"
          min="0"
          step="any"
          value={goalCarbs}
          onChange={(event) => setGoalCarbs(event.target.value)}
          required
        />

        <label htmlFor="goal-fat">Fat (g)</label>
        <input
          id="goal-fat"
          type="number"
          min="0"
          step="any"
          value={goalFat}
          onChange={(event) => setGoalFat(event.target.value)}
          required
        />

        <label htmlFor="goal-water">Water (ml)</label>
        <input
          id="goal-water"
          type="number"
          min="0"
          step="1"
          value={goalWater}
          onChange={(event) => setGoalWater(event.target.value)}
          required
        />

        {goalSaveError && (
          <p className="error-message">{goalSaveError}</p>
        )}

        {goalSaveSuccess && (
          <p role="status">Daily goals saved successfully.</p>
        )}

        <div className="form-actions">
          <button type="submit" disabled={savingGoals || goalsLoading}>
            {savingGoals ? 'Saving...' : 'Save daily goals'}
          </button>
        </div>
      </form>
      <form className="form-card" onSubmit={handleSubmit}>
        <h2>Log a meal</h2>
        <p>Enter the nutritional information for your meal.</p>

        <label htmlFor="meal-type">Meal type</label>
        <select
          id="meal-type"
          value={mealType}
          onChange={(event) => setMealType(event.target.value)}
        >
          <option value="Breakfast">Breakfast</option>
          <option value="Lunch">Lunch</option>
          <option value="Dinner">Dinner</option>
          <option value="Snack">Snack</option>
        </select>

        <label htmlFor="meal-description">Description</label>
        <input
          id="meal-description"
          type="text"
          maxLength={200}
          placeholder="e.g. Chicken, rice and vegetables"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          required
        />

        <label htmlFor="meal-calories">Calories (kcal)</label>
        <input
          id="meal-calories"
          type="number"
          min="0"
          step="any"
          placeholder="e.g. 550"
          value={calories}
          onChange={(event) => setCalories(event.target.value)}
        />

        <label htmlFor="meal-protein">Protein (g)</label>
        <input
          id="meal-protein"
          type="number"
          min="0"
          step="any"
          placeholder="e.g. 35"
          value={protein}
          onChange={(event) => setProtein(event.target.value)}
        />

        <label htmlFor="meal-carbs">Carbohydrates (g)</label>
        <input
          id="meal-carbs"
          type="number"
          min="0"
          step="any"
          placeholder="e.g. 60"
          value={carbs}
          onChange={(event) => setCarbs(event.target.value)}
        />

        <label htmlFor="meal-fat">Fat (g)</label>
        <input
          id="meal-fat"
          type="number"
          min="0"
          step="any"
          placeholder="e.g. 15"
          value={fat}
          onChange={(event) => setFat(event.target.value)}
        />

        <label htmlFor="meal-water">Water (ml)</label>
        <input
          id="meal-water"
          type="number"
          min="0"
          step="1"
          placeholder="e.g. 500"
          value={water}
          onChange={(event) => setWater(event.target.value)}
        />

        {saveError && <p className="error-message">{saveError}</p>}

        <div className="form-actions">
          <button type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save meal'}
          </button>
        </div>
      </form>

      <div className="section-heading">
        <h2>Meal history</h2>
      </div>

      {loading && (
        <div className="loading-card" role="status">
          Loading nutrition entries...
        </div>
      )}

      {error && (
        <div className="error-card" role="alert">
          <p>Could not load nutrition: {error}</p>
          <button type="button" onClick={retry}>Try again</button>
        </div>
      )}

      {data && !loading && (
        data.length === 0 ? (
          <div className="empty-card">
            <span aria-hidden="true">+</span>
            <strong>No meals recorded</strong>
            <p>Your registered meals will appear here.</p>
          </div>
        ) : (
          <div className="workout-list">
            {[...data]
              .sort(
                (a, b) =>
                  new Date(b.logged_at).getTime() -
                  new Date(a.logged_at).getTime()
              )
              .map((entry) => (
                <article className="workout-item" key={entry.id}>
                  <div className="workout-item-icon" aria-hidden="true">
                    🍽
                  </div>

                  <div className="workout-item-main">
                    <strong>{entry.description}</strong>
                    <small>
                      {entry.meal_type} ·{' '}
                      {new Date(entry.logged_at).toLocaleString()}
                    </small>
                    <small>
                      Protein: {entry.protein ?? '—'} g ·
                      Carbs: {entry.carbs ?? '—'} g ·
                      Fat: {entry.fat ?? '—'} g
                    </small>
                  </div>

                  <div className="workout-item-numbers">
                    <strong>{entry.calories ?? '—'}</strong>
                    <small>kcal</small>
                  </div>
                </article>
              ))}
          </div>
        )
      )}
    </div>
  )
}
