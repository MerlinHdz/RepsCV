
from fastapi.testclient import TestClient
from backend.main import create_app

from pathlib import Path
from tempfile import TemporaryDirectory


with TemporaryDirectory() as temp_dir:

    # 1. Create an isolated test database
    db_path = Path(temp_dir) / "nutrition_test.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    app = create_app(database_url=database_url)

    with TestClient(app) as client:

        # 2. Register a test user
        response = client.post(
            "/api/auth/register",
            json={
                "username": "nutrition_api_test",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 201, response.text

        csrf_token = response.json()["csrf_token"]

        print("Test user registered successfully!")

        # 3. Create a nutrition entry through POST
        response = client.post(
            "/api/nutrition",
            headers={"x-csrf-token": csrf_token},
            json={
                "meal_type": "lunch",
                "description": "Chicken rice",
                "calories": 650,
                "protein": 35,
                "carbs": 70,
                "fat": 18,
            },
        )

        assert response.status_code == 201, response.text

        created_entry = response.json()

        print("Nutrition entry created:", created_entry)

        # 4. Retrieve entries through GET
        response = client.get("/api/nutrition")

        assert response.status_code == 200, response.text

        entries = response.json()

        assert len(entries) == 1
        assert entries[0]["description"] == "Chicken rice"
        assert entries[0]["calories"] == 650

        print("Nutrition entries retrieved successfully!")

        print("\nALL API TESTS PASSED!")
