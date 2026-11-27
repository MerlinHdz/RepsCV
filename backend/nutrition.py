from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.database import NutritionEntry


def create_entry(
    db: Session,
    user_id: int,
    meal_type: str,
    description: str,
    calories: float | None = None,
    protein: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    water_ml: int | None = None,
):
    entry = NutritionEntry(
        user_id=user_id,
        logged_at=datetime.now(timezone.utc),
        meal_type=meal_type,
        description=description,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        water_ml=water_ml,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


def get_entries(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
):
    statement = (
        select(NutritionEntry)
        .where(NutritionEntry.user_id == user_id)
        .where(NutritionEntry.logged_at >= start)
        .where(NutritionEntry.logged_at < end)
        .order_by(NutritionEntry.logged_at.desc())
    )

    return db.scalars(statement).all()


def daily_summary(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime,
):
    entries = get_entries(db, user_id, start, end)

    return {
        "calories": sum(e.calories or 0 for e in entries),
        "protein": sum(e.protein or 0 for e in entries),
        "carbs": sum(e.carbs or 0 for e in entries),
        "fat": sum(e.fat or 0 for e in entries),
        "water_ml": sum(e.water_ml or 0 for e in entries),
    }

def update_entry(
    db: Session,
    user_id: int,
    entry_id: int,
    meal_type: str | None = None,
    description: str | None = None,
    calories: float | None = None,
    protein: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    water_ml: int | None = None,
):
    statement = (
        select(NutritionEntry)
        .where(NutritionEntry.id == entry_id)
        .where(NutritionEntry.user_id == user_id)
    )

    entry = db.scalars(statement).first()

    if entry is None:
        return None

    if meal_type is not None:
        entry.meal_type = meal_type

    if description is not None:
        entry.description = description

    if calories is not None:
        entry.calories = calories

    if protein is not None:
        entry.protein = protein

    if carbs is not None:
        entry.carbs = carbs

    if fat is not None:
        entry.fat = fat

    if water_ml is not None:
        entry.water_ml = water_ml

    db.commit()
    db.refresh(entry)

    return entry

def delete_entry(
    db: Session,
    user_id: int,
    entry_id: int,
):
    statement = (
        select(NutritionEntry)
        .where(NutritionEntry.id == entry_id)
        .where(NutritionEntry.user_id == user_id)
    )

    entry = db.scalars(statement).first()

    if entry is None:
        return False

    db.delete(entry)
    db.commit()

    return True