"""Server-side pose validation and repetition counting."""

from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class Thresholds:
    min_visibility: float = 0.55
    min_presence: float = 0.55
    min_body_angle: float = 155.0
    min_horizontal_fraction: float = 0.68
    max_shoulder_width_fraction: float = 0.75
    max_arm_difference: float = 35.0
    top_angle: float = 155.0
    bottom_angle: float = 105.0
    stable_frames: int = 3
    stable_seconds: float = 0.08
    min_rep_seconds: float = 0.35
    lost_after_seconds: float = 0.75


DEFAULT_THRESHOLDS = Thresholds()
PARTS = ("shoulder", "elbow", "wrist", "hip", "ankle")


def _point(landmarks, name, thresholds):
    value = landmarks.get(name)
    if not isinstance(value, dict):
        return None
    fields = [value.get("x"), value.get("y"), value.get("visibility"),
              value.get("presence", value.get("visibility"))]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in fields):
        return None
    x, y, visibility, presence = fields
    if not (-0.25 <= x <= 1.25 and -0.25 <= y <= 1.25):
        return None
    if visibility < thresholds.min_visibility or presence < thresholds.min_presence:
        return None
    return (float(x), float(y))


def _angle(a, b, c, aspect):
    ax, ay = (a[0] - b[0]) * aspect, a[1] - b[1]
    cx, cy = (c[0] - b[0]) * aspect, c[1] - b[1]
    length = math.hypot(ax, ay) * math.hypot(cx, cy)
    if length < 1e-8:
        return None
    return math.degrees(math.acos(max(-1.0, min(1.0, (ax * cx + ay * cy) / length))))


def assess_pose(frame, thresholds=DEFAULT_THRESHOLDS):
    """Return tracking status, validity, feedback, angles, and visible arms."""
    if frame.get("landmarks") is None:
        return "lost", False, "Move into view so your whole body is visible.", None, None, ()
    landmarks = frame["landmarks"]
    aspect = frame["aspect_ratio"]
    points = {f"{side}_{part}": _point(landmarks, f"{side}_{part}", thresholds)
              for side in ("left", "right") for part in PARTS}
    arms, bodies = {}, []
    for side in ("left", "right"):
        shoulder, elbow, wrist, hip, ankle = (points[f"{side}_{part}"] for part in PARTS)
        if shoulder and elbow and wrist:
            angle = _angle(shoulder, elbow, wrist, aspect)
            if angle is not None:
                arms[side] = angle
        if shoulder and hip and ankle:
            body_angle = _angle(shoulder, hip, ankle, aspect)
            run = abs((shoulder[0] - ankle[0]) * aspect)
            length = math.hypot(run, shoulder[1] - ankle[1])
            if body_angle is not None and length > 0.05:
                bodies.append((body_angle, run / length, length))
    if not arms or not bodies:
        return "limited", False, "Show one full arm and your shoulder, hip, and ankle.", None, None, ()
    visible_sides = tuple(arms)
    elbow_angle = sum(arms.values()) / len(arms)
    body_angle = sum(body[0] for body in bodies) / len(bodies)
    if any(body[0] < thresholds.min_body_angle for body in bodies):
        return "tracked", False, "Keep your shoulders, hips, and ankles in one line.", elbow_angle, body_angle, visible_sides
    if any(body[1] < thresholds.min_horizontal_fraction for body in bodies):
        return "tracked", False, "Set the camera to your side and get into a floor push-up position.", elbow_angle, body_angle, visible_sides
    left, right = points["left_shoulder"], points["right_shoulder"]
    if left and right:
        width = math.hypot((left[0] - right[0]) * aspect, left[1] - right[1])
        if width / min(body[2] for body in bodies) > thresholds.max_shoulder_width_fraction:
            return "tracked", False, "Turn sideways to the camera.", elbow_angle, body_angle, visible_sides
    if len(arms) == 2 and abs(arms["left"] - arms["right"]) > thresholds.max_arm_difference:
        return "tracked", False, "Bend and straighten both elbows together.", elbow_angle, body_angle, visible_sides
    return "tracked", True, "Good position. Lower your chest, then press up.", elbow_angle, body_angle, visible_sides


class RepCounter:
    def __init__(self, thresholds=DEFAULT_THRESHOLDS):
        self.thresholds = thresholds
        self.reps = 0
        self.state = "UNKNOWN"
        self._candidate = None
        self._candidate_frames = 0
        self._candidate_since = None
        self._cycle_started = None
        self._last_frame_at = None
        self._side = None

    def _reset_phase(self):
        self.state = "UNKNOWN"
        self._candidate = None
        self._candidate_frames = 0
        self._candidate_since = None
        self._cycle_started = None
        self._side = None

    def _response(self, tracking, valid, feedback, elbow=None, body=None):
        return {
            "reps": self.reps, "state": self.state, "tracking": tracking,
            "form_valid": valid, "feedback": feedback,
            "elbow_angle": round(elbow, 1) if elbow is not None else None,
            "body_angle": round(body, 1) if body is not None else None,
        }

    def error_response(self, message):
        # A malformed frame interrupts the movement just like lost tracking.
        self._reset_phase()
        return {**self._response("error", False, message), "error": message}

    def update(self, frame, now=None):
        now = time.monotonic() if now is None else now
        if self._last_frame_at is not None and now - self._last_frame_at > self.thresholds.lost_after_seconds:
            self._reset_phase()
        self._last_frame_at = now
        tracking, valid, feedback, elbow, body, visible_sides = assess_pose(frame, self.thresholds)
        if not valid:
            self._reset_phase()
            return self._response(tracking, False, feedback, elbow, body)
        if self._side is not None and self._side not in visible_sides:
            self._reset_phase()
            return self._response("limited", False, "Keep the same arm visible through the rep.", elbow, body)
        if self.state != "UNKNOWN" and self._side is None and len(visible_sides) == 1:
            self._side = visible_sides[0]

        zone = "UP" if elbow >= self.thresholds.top_angle else "DOWN" if elbow <= self.thresholds.bottom_angle else None
        if zone is None:
            self._candidate = None
            self._candidate_frames = 0
            self._candidate_since = None
        elif zone != self._candidate:
            self._candidate = zone
            self._candidate_frames = 1
            self._candidate_since = now
        else:
            self._candidate_frames += 1

        stable = (zone is not None and self._candidate_frames >= self.thresholds.stable_frames
                  and now - self._candidate_since >= self.thresholds.stable_seconds)
        if stable and zone == "UP":
            if self.state == "DOWN" and now - self._cycle_started >= self.thresholds.min_rep_seconds:
                self.reps += 1
                feedback = "Rep counted. Lower with control for the next one."
            if self.state != "UP":
                self.state = "UP"
                self._cycle_started = now
                if len(visible_sides) == 1:
                    self._side = visible_sides[0]
        elif stable and zone == "DOWN" and self.state == "UP":
            self.state = "DOWN"
            feedback = "Depth reached. Press back up."
        elif self.state == "UNKNOWN":
            feedback = "Hold the top position to start a rep."
        elif self.state == "UP":
            feedback = "Lower until your elbows bend to about 100°."
        elif self.state == "DOWN":
            feedback = "Press up until your elbows are nearly straight."
        return self._response(tracking, True, feedback, elbow, body)
