class RepCounter:
    def __init__(self):
        self.reps = 0
        self.state = "UNKNOWN"

    def update(self, angle: float) -> int:
        if angle >= 160:
            if self.state == "DOWN":
                self.reps += 1

            self.state = "UP"

        elif angle <= 90:
            if self.state == "UP":
                self.state = "DOWN"

        return self.reps