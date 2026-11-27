
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import NutritionGoal


def get_goals(db: Session, user_id: int):
    statement = (
        select(NutritionGoal)
        .where(NutritionGoal.user_id == user_id)
    )

    goals = db.scalars(statement).first()

    if goals is None:
        goals = NutritionGoal(user_id=user_id)

        db.add(goals)
        db.commit()
        db.refresh(goals)

    return goals


def update_goals(
    db: Session,
    user_id: int,
    calories: float | None = None,
    protein: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    water_ml: int | None = None,
):
    goals = get_goals(db, user_id)

    if calories is not None:
        goals.calories = calories

    if protein is not None:
        goals.protein = protein

    if carbs is not None:
        goals.carbs = carbs

    if fat is not None:
        goals.fat = fat

    if water_ml is not None:
        goals.water_ml = water_ml

    db.commit()
    db.refresh(goals)

    return goals