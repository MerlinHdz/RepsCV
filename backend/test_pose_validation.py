"""Boundary and degraded-landmark cases for the Python pose gate."""

import unittest

from backend.workouts import validate_pose_message
from backend.rep_counter import RepCounter, Thresholds, assess_pose
from backend.test_rep_counter import frame, hold, wire


class PoseValidationTests(unittest.TestCase):
    def test_missing_presence_uses_visibility_when_model_omits_it(self):
        pose = frame(170)
        for landmark in pose["landmarks"].values():
            landmark.pop("presence")
        tracking, valid, _, elbow, body, sides = assess_pose(pose)
        self.assertEqual(tracking, "tracked")
        self.assertTrue(valid)
        self.assertAlmostEqual(elbow, 170)
        self.assertAlmostEqual(body, 180)
        self.assertEqual(sides, ("left", "right"))

    def test_low_confidence_far_arm_does_not_block_near_arm(self):
        pose = frame(170)
        for name, landmark in pose["landmarks"].items():
            if name.startswith("right"):
                landmark["visibility"] = 0.2
                landmark["presence"] = 0.2
        self.assertEqual(assess_pose(pose)[-1], ("left",))
        counter = RepCounter()
        for angle, time in ((170, 0), (90, 0.25), (170, 0.55)):
            pose = frame(angle)
            for name, landmark in pose["landmarks"].items():
                if name.startswith("right"):
                    landmark["visibility"] = landmark["presence"] = 0.2
            for index in range(3):
                result = counter.update(pose, now=time + index * 0.05)
        self.assertEqual(result["reps"], 1)

    def test_missing_landmark_prevents_count_and_requests_visibility(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        pose = frame(90)
        for side in ("left", "right"):
            pose["landmarks"].pop(f"{side}_wrist")
        result = counter.update(pose, now=0.25)
        self.assertFalse(result["form_valid"])
        self.assertEqual(result["tracking"], "limited")
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertIn("full arm", result["feedback"])

    def test_nonfinite_and_out_of_range_landmarks_are_unusable(self):
        for bad_x in (float("nan"), float("inf"), 4, "0.2", True):
            with self.subTest(bad_x=bad_x):
                pose = frame(170, right=False)
                pose["landmarks"]["left_elbow"]["x"] = bad_x
                tracking, valid, *_ = assess_pose(pose)
                self.assertEqual(tracking, "limited")
                self.assertFalse(valid)

    def test_thresholds_can_be_tuned_without_changing_counter_logic(self):
        strict = Thresholds(min_visibility=0.95)
        loose = Thresholds(min_visibility=0.5)
        pose = frame(170, confidence=0.8)
        self.assertFalse(assess_pose(pose, strict)[1])
        self.assertTrue(assess_pose(pose, loose)[1])

    def test_invalid_aspect_and_payload_shapes_are_rejected(self):
        for aspect in (0, -1, 5, "1", True, float("inf")):
            with self.subTest(aspect=aspect):
                self.assertFalse(validate_pose_message(wire({"aspect_ratio": aspect, "landmarks": None})))
        self.assertFalse(validate_pose_message([frame()]))
        self.assertFalse(validate_pose_message(wire({"aspect_ratio": 1, "landmarks": [1, 2]})))


if __name__ == "__main__":
    unittest.main()
