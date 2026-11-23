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
    secondary_confidence: float = 0.75
    top_angle: float = 155.0
    bottom_angle: float = 105.0
    stable_frames: int = 2
    stable_seconds: float = 0.08
    endpoint_hysteresis: float = 4.0
    candidate_window_seconds: float = 0.3
    occlusion_grace_seconds: float = 0.25
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


def _confidence(landmarks, side, parts):
    """Weakest landmark confidence; called only after point validation."""
    return min(min(landmarks[f"{side}_{part}"]["visibility"],
                   landmarks[f"{side}_{part}"].get("presence", landmarks[f"{side}_{part}"]["visibility"]))
               for part in parts)


def assess_pose(frame, thresholds=DEFAULT_THRESHOLDS, preferred_side=None):
    """Return tracking status, validity, feedback, angles, and visible arms."""
    if frame.get("landmarks") is None:
        return "lost", False, "Move into view so your whole body is visible.", None, None, ()
    landmarks = frame["landmarks"]
    aspect = frame["aspect_ratio"]
    points = {f"{side}_{part}": _point(landmarks, f"{side}_{part}", thresholds)
              for side in ("left", "right") for part in PARTS}
    arms, arm_confidence, bodies = {}, {}, []
    for side in ("left", "right"):
        shoulder, elbow, wrist, hip, ankle = (points[f"{side}_{part}"] for part in PARTS)
        if shoulder and elbow and wrist:
            angle = _angle(shoulder, elbow, wrist, aspect)
            if angle is not None:
                arms[side] = angle
                arm_confidence[side] = _confidence(landmarks, side, ("shoulder", "elbow", "wrist"))
        if shoulder and hip and ankle:
            body_angle = _angle(shoulder, hip, ankle, aspect)
            run = abs((shoulder[0] - ankle[0]) * aspect)
            length = math.hypot(run, shoulder[1] - ankle[1])
            if body_angle is not None and length > 0.05:
                bodies.append((body_angle, run / length, length,
                               _confidence(landmarks, side, ("shoulder", "hip", "ankle"))))
    if not arms or not bodies:
        return "limited", False, "Show one full arm and your shoulder, hip, and ankle.", None, None, ()
    visible_sides = tuple(sorted(arms, key=lambda side: -arm_confidence[side]))
    if preferred_side is not None and preferred_side not in arms:
        return "limited", False, "Keep the same arm visible through the rep.", None, None, visible_sides
    # Measure one consistent arm, not a shifting average of near/far projections.
    elbow_angle = arms[preferred_side or visible_sides[0]]
    best_body = max(bodies, key=lambda body: body[3])
    bodies = [body for body in bodies if body is best_body or body[3] >= thresholds.secondary_confidence]
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
    if (len(arms) == 2 and min(arm_confidence.values()) >= thresholds.secondary_confidence
            and abs(arms["left"] - arms["right"]) > thresholds.max_arm_difference):
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
        self._last_valid_at = None
        self._occluded = False
        self._side = None

    def _clear_candidate(self):
        self._candidate = None
        self._candidate_frames = 0
        self._candidate_since = None

    def _reset_phase(self):
        self.state = "UNKNOWN"
        self._clear_candidate()
        self._cycle_started = None
        self._last_valid_at = None
        self._occluded = False
        self._side = None

    def _response(self, tracking, valid, feedback, elbow=None, body=None):
        return {
            "reps": self.reps, "state": self.state, "tracking": tracking,
            "form_valid": valid, "feedback": feedback,
            "elbow_angle": round(elbow, 1) if elbow is not None else None,
            "body_angle": round(body, 1) if body is not None else None,
            "measured_side": self._side,
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
        # A short occlusion can preserve an already proven phase, never evidence
        # toward a new endpoint. Longer blind intervals require a fresh top.
        if (self._occluded and self._last_valid_at is not None
                and now - self._last_valid_at > self.thresholds.occlusion_grace_seconds):
            self._reset_phase()
        tracking, valid, feedback, elbow, body, visible_sides = assess_pose(frame, self.thresholds, self._side)
        if not valid:
            self._clear_candidate()
            self._occluded = True
            if (tracking == "tracked"  # Observed bad form is not an occlusion.
                    or (self._last_valid_at is not None
                        and now - self._last_valid_at > self.thresholds.occlusion_grace_seconds)):
                self._reset_phase()
            return self._response(tracking, False, feedback, elbow, body)
        self._occluded = False
        self._last_valid_at = now
        if self._side is None:
            self._side = visible_sides[0]

        zone = "UP" if elbow >= self.thresholds.top_angle else "DOWN" if elbow <= self.thresholds.bottom_angle else None
        if self.state == "UP" and zone == "UP":
            # The top is already proven; keep the cycle origin at its last observation.
            self._cycle_started = now
        if (self._candidate_since is not None
                and now - self._candidate_since > self.thresholds.candidate_window_seconds):
            self._clear_candidate()
        if zone is None:
            near_top = self._candidate == "UP" and elbow >= self.thresholds.top_angle - self.thresholds.endpoint_hysteresis
            near_bottom = self._candidate == "DOWN" and elbow <= self.thresholds.bottom_angle + self.thresholds.endpoint_hysteresis
            if not (near_top or near_bottom):
                self._clear_candidate()
        elif zone != self._candidate:
            self._candidate = zone
            self._candidate_frames = 1
            self._candidate_since = now
        else:
            self._candidate_frames += 1

        stable = (zone is not None and self._candidate_frames >= self.thresholds.stable_frames
                  and now - self._candidate_since + 1e-9 >= self.thresholds.stable_seconds)
        if stable and zone == "UP":
            if self.state == "DOWN" and now - self._cycle_started >= self.thresholds.min_rep_seconds:
                self.reps += 1
                feedback = "Rep counted. Lower with control for the next one."
            self.state = "UP"
            self._cycle_started = now
        elif stable and zone == "DOWN" and self.state == "UP":
            self.state = "DOWN"
            feedback = "Depth reached. Press back up."
        elif self.state == "UNKNOWN":
            feedback = "Hold the top position to start a rep."
        elif self.state == "UP":
            feedback = "Top confirmed. Lower your chest to reach push-up depth."
        elif self.state == "DOWN":
            feedback = "Press up until your elbows are nearly straight."
        return self._response(tracking, True, feedback, elbow, body)
