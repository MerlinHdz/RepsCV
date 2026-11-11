class RepCounter:
    def __init__(self):
        self.reps = 0
        self.state = "UNKNOWN"

    def update(self, angle: float, body_angle: float) -> int:
    # Reject measurements when the body is too bent.
        if body_angle < 150:
            self.state = "UNKNOWN"
            return self.reps

        # Arms extended
        if angle >= 160:
            if self.state == "DOWN":
                self.reps += 1

            self.state = "UP"

        # Arms bent
        elif angle <= 90:
            if self.state == "UP":
                self.state = "DOWN"

        return self.reps