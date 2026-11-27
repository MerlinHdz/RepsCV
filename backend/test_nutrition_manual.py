
from datetime import datetime, timedelta, timezone

from backend.database import Base, User, make_database
from backend.nutrition import (
    create_entry,
    get_entries,
    daily_summary,
    update_entry,
    delete_entry,
)

engine, SessionLocal = make_database("sqlite:///:memory:")
Base.metadata.create_all(engine)

try:
    with SessionLocal() as db:

        # 1. Create test user
        user = User(
            username="nutrition_test",
            password_hash="test-only",
            department=None,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print("Test user created:", user.id)

        # 2. Create two meals
        create_entry(
            db, user.id, "breakfast", "Eggs and toast",
            calories=400, protein=20, carbs=35, fat=15,
        )

        create_entry(
            db, user.id, "lunch", "Chicken rice",
            calories=650, protein=35, carbs=70, fat=18,
        )

        print("Two meals saved successfully!")

        # 3. Retrieve entries
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=1)
        end = now + timedelta(days=1)

        entries = get_entries(db, user.id, start, end)

        assert len(entries) == 2
        print("Retrieved", len(entries), "meals successfully!")

        # 4. Test daily summary
        summary = daily_summary(db, user.id, start, end)

        assert summary["calories"] == 1050
        assert summary["protein"] == 55
        assert summary["carbs"] == 105
        assert summary["fat"] == 33

        print("Initial summary:", summary)

        # 5. Test updating lunch
        lunch = next(e for e in entries if e.meal_type == "lunch")

        updated = update_entry(
            db=db,
            user_id=user.id,
            entry_id=lunch.id,
            description="Chicken rice (updated)",
            calories=700,
        )

        assert updated is not None
        assert updated.description == "Chicken rice (updated)"
        assert updated.calories == 700

        print("Update test passed!")

        # 6. Test deleting breakfast
        breakfast = next(e for e in entries if e.meal_type == "breakfast")

        deleted = delete_entry(
            db=db,
            user_id=user.id,
            entry_id=breakfast.id,
        )

        assert deleted is True

        remaining = get_entries(db, user.id, start, end)
        assert len(remaining) == 1
        assert remaining[0].description == "Chicken rice (updated)"

        print("Delete test passed!")

        # 7. Verify final summary
        final_summary = daily_summary(db, user.id, start, end)

        assert final_summary["calories"] == 700
        assert final_summary["protein"] == 35
        assert final_summary["carbs"] == 70
        assert final_summary["fat"] == 18

        print("Final summary:", final_summary)
        print("\nALL TESTS PASSED!")

finally:
    engine.dispose()
