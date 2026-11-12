import math
import unittest

from backend.workouts import validate_pose_message
from backend.rep_counter import RepCounter


def frame(elbow_angle=170, *, hip_y=0.5, standing=False, left=True, right=True,
          right_angle=None, confidence=0.99):
    points = {}
    for side, enabled, angle, offset in (
        ("left", left, elbow_angle, 0),
        ("right", right, right_angle if right_angle is not None else elbow_angle, 0.03),
    ):
        if not enabled:
            continue
        if standing:
            shoulder, hip, ankle = (0.45 + offset, 0.15), (0.45 + offset, 0.5), (0.45 + offset, 0.85)
        else:
            shoulder, hip, ankle = (0.22 + offset, 0.5), (0.48 + offset, hip_y), (0.78 + offset, 0.5)
        elbow = (shoulder[0] - 0.07, shoulder[1])
        wrist = (elbow[0] + 0.07 * math.cos(math.radians(angle)),
                 elbow[1] + 0.07 * math.sin(math.radians(angle)))
        for part, (x, y) in zip(("shoulder", "elbow", "wrist", "hip", "ankle"),
                                (shoulder, elbow, wrist, hip, ankle)):
            points[f"{side}_{part}"] = {"x": x, "y": y, "visibility": confidence, "presence": confidence}
    return {"aspect_ratio": 1, "landmarks": points}


def wire(pose, sequence=0):
    return {"type": "landmarks", "sequence": sequence, "timestamp_ms": sequence * 50,
            "aspect_ratio": pose["aspect_ratio"], "points": pose["landmarks"]}


def hold(counter, angle, start, **kwargs):
    result = None
    for index in range(3):
        result = counter.update(frame(angle, **kwargs), now=start + index * 0.05)
    return result


class RepCounterTests(unittest.TestCase):
    def test_complete_rep_requires_stable_top_bottom_top(self):
        counter = RepCounter()
        self.assertEqual(hold(counter, 170, 0)["state"], "UP")
        self.assertEqual(hold(counter, 90, 0.25)["state"], "DOWN")
        result = hold(counter, 170, 0.55)
        self.assertEqual((result["reps"], result["state"], result["form_valid"]), (1, "UP", True))
        self.assertEqual(hold(counter, 170, 0.75)["reps"], 1)

    def test_one_visible_arm_is_sufficient(self):
        counter = RepCounter()
        hold(counter, 170, 0, right=False)
        hold(counter, 90, 0.25, right=False)
        self.assertEqual(hold(counter, 170, 0.55, right=False)["reps"], 1)

    def test_switching_single_visible_arm_cancels_unfinished_rep(self):
        counter = RepCounter()
        hold(counter, 170, 0, right=False)
        result = counter.update(frame(90, left=False), now=0.25)
        self.assertEqual((result["state"], result["tracking"]), ("UNKNOWN", "limited"))
        self.assertEqual(hold(counter, 170, 0.55, left=False)["reps"], 0)

    def test_partial_rep_and_one_frame_spike_do_not_count(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 130, 0.25)
        self.assertEqual(hold(counter, 170, 0.55)["reps"], 0)
        counter.update(frame(90), now=0.8)
        self.assertEqual(hold(counter, 170, 0.9)["reps"], 0)

    def test_bad_alignment_and_standing_curl_reset_phase(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        result = hold(counter, 90, 0.25, hip_y=0.72)
        self.assertFalse(result["form_valid"])
        self.assertEqual(result["state"], "UNKNOWN")
        result = hold(counter, 90, 0.5, standing=True)
        self.assertFalse(result["form_valid"])
        self.assertIn("side", result["feedback"])
        self.assertEqual(hold(counter, 170, 0.8)["reps"], 0)

    def test_visibility_and_asymmetric_arms(self):
        counter = RepCounter()
        self.assertEqual(hold(counter, 170, 0, confidence=0.2)["tracking"], "limited")
        self.assertFalse(counter.update(frame(90, right_angle=170), now=0.3)["form_valid"])
        self.assertEqual(counter.state, "UNKNOWN")

    def test_front_facing_shoulder_separation_is_rejected(self):
        pose = frame(170)
        for name, point in pose["landmarks"].items():
            point["x"] += -0.15 if name.startswith("left") else 0.3
        result = RepCounter().update(pose, now=0)
        self.assertFalse(result["form_valid"])
        self.assertIn("sideways", result["feedback"])

    def test_stable_frames_also_need_elapsed_time(self):
        counter = RepCounter()
        for _ in range(5):
            result = counter.update(frame(170), now=0)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(counter.update(frame(170), now=0.1)["state"], "UP")

    def test_too_fast_cycle_is_not_counted(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 90, 0.15)
        result = hold(counter, 170, 0.3)
        self.assertEqual(result["state"], "UP")
        self.assertEqual(result["reps"], 0)

    def test_tracking_loss_and_timeout_require_new_top(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 90, 0.25)
        lost = counter.update({"aspect_ratio": 1, "landmarks": None}, now=0.4)
        self.assertEqual((lost["tracking"], lost["state"]), ("lost", "UNKNOWN"))
        self.assertEqual(hold(counter, 170, 0.55)["reps"], 0)
        hold(counter, 90, 0.8)
        self.assertEqual(counter.update(frame(170), now=2.0)["state"], "UNKNOWN")
        self.assertEqual(hold(counter, 170, 2.1)["reps"], 0)

    def test_new_complete_cycle_after_tracking_recovery_counts(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 90, 0.25)
        counter.update({"aspect_ratio": 1, "landmarks": None}, now=0.4)
        hold(counter, 170, 0.6)
        hold(counter, 90, 0.85)
        self.assertEqual(hold(counter, 170, 1.15)["reps"], 1)

    def test_invalid_protocol_frame(self):
        self.assertFalse(validate_pose_message(wire({"aspect_ratio": float("nan"), "landmarks": None})))
        self.assertFalse(validate_pose_message(wire({"aspect_ratio": 1, "landmarks": []})))
        self.assertTrue(validate_pose_message(wire(frame())))


if __name__ == "__main__":
    unittest.main()
