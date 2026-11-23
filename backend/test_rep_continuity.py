"""Real-cadence synthetic regressions: continuity without guessing unseen reps.

These sequences exercise the counter's sampling behavior, not camera accuracy.
"""

import math
import unittest

from backend.rep_counter import RepCounter
from backend.test_helpers import ApiCase
from backend.test_rep_counter import frame, hold, wire


def far_arm_pose(angle, far_angle):
    pose = frame(angle, right_angle=far_angle)
    for name, point in pose["landmarks"].items():
        if name.startswith("right"):
            point["visibility"] = point["presence"] = 0.6
    return pose


class ContinuityTests(unittest.TestCase):
    def test_two_endpoint_frames_at_browser_cadence_count_without_holding(self):
        counter = RepCounter()
        angles = [170, 165, 140, 120, 100, 95, 120, 140, 160, 170]
        for index, angle in enumerate(angles):
            result = counter.update(frame(angle), now=index * 0.08)
            self.assertEqual(result["reps"], int(index == len(angles) - 1))

    def test_smooth_reps_at_different_sample_rates_and_offsets(self):
        for fps in (8, 12.5, 20, 30):
            for offset in (0, 0.025, 0.06):
                with self.subTest(fps=fps, offset=offset):
                    counter = RepCounter()
                    hold(counter, 170, 0)
                    period = 1.6
                    for index in range(math.ceil((period * 4 + 0.2) * fps)):
                        elapsed = index / fps + offset
                        angle = 130 + 40 * math.cos(2 * math.pi * elapsed / period)
                        result = counter.update(frame(angle), now=0.2 + elapsed)
                    self.assertEqual(result["reps"], 4)

    def test_weak_far_arm_does_not_average_away_real_depth(self):
        counter = RepCounter()
        for angle, far, start in ((165, 165, 0), (100, 135, 0.25), (165, 165, 0.55)):
            for index in range(3):
                result = counter.update(far_arm_pose(angle, far), now=start + index * 0.05)
        self.assertEqual(result["reps"], 1)
        self.assertEqual(result["measured_side"], "left")

    def test_confidence_changes_do_not_switch_measured_arm(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        pose = frame(100, right_angle=125)
        for name, point in pose["landmarks"].items():
            if name.startswith("left"):
                point["visibility"] = point["presence"] = 0.8
        for now in (0.25, 0.35):
            result = counter.update(pose, now=now)
        self.assertEqual((result["measured_side"], result["elbow_angle"], result["state"]),
                         ("left", 100, "DOWN"))
        self.assertEqual(hold(counter, 170, 0.55)["reps"], 1)

    def test_selects_strongest_arm_initially_and_checks_both_reliable_arms(self):
        pose = frame(165)
        pose["landmarks"]["left_wrist"]["visibility"] = 0.6
        counter = RepCounter()
        self.assertEqual(counter.update(pose, now=0)["measured_side"], "right")
        result = counter.update(frame(90, right_angle=170), now=0.1)
        self.assertFalse(result["form_valid"])
        self.assertEqual(result["state"], "UNKNOWN")

    def test_short_occlusion_preserves_proven_bottom_but_never_counts_itself(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 90, 0.25)
        result = counter.update({"landmarks": None}, now=0.43)
        self.assertEqual((result["state"], result["reps"], result["form_valid"]), ("DOWN", 0, False))
        self.assertEqual(hold(counter, 170, 0.51)["reps"], 1)

    def test_occlusion_during_unconfirmed_bottom_cannot_supply_depth(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        counter.update(frame(90), now=0.25)
        counter.update({"landmarks": None}, now=0.33)
        counter.update(frame(90), now=0.41)
        self.assertEqual(hold(counter, 170, 0.49)["reps"], 0)

    def test_long_occlusion_or_observed_bad_form_cancels_proven_bottom(self):
        for invalid in (None, frame(90, hip_y=0.72), frame(90, standing=True)):
            with self.subTest(invalid=invalid is None):
                counter = RepCounter()
                hold(counter, 170, 0)
                hold(counter, 90, 0.25)
                counter.update(invalid or {"landmarks": None}, now=0.43)
                self.assertEqual(hold(counter, 170, 0.65)["reps"], 0)

    def test_hysteresis_tolerates_jitter_but_still_needs_two_depth_observations(self):
        for bottom, expected in (([104, 107, 103], 1), ([104, 107, 108], 0), ([106, 107, 106], 0)):
            with self.subTest(bottom=bottom):
                counter = RepCounter()
                hold(counter, 170, 0)
                for index, angle in enumerate(bottom):
                    counter.update(frame(angle), now=0.25 + index * 0.08)
                self.assertEqual(hold(counter, 170, 0.55)["reps"], expected)

    def test_candidate_expires_and_sparse_noise_cannot_accumulate(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        for index, angle in enumerate([104, 107, 107, 107, 107, 104]):
            counter.update(frame(angle), now=0.2 + index * 0.08)
        self.assertEqual(hold(counter, 170, 0.7)["reps"], 0)

    def test_brief_single_frame_top_does_not_complete_rep(self):
        counter = RepCounter()
        hold(counter, 170, 0)
        hold(counter, 90, 0.25)
        counter.update(frame(170), now=0.55)
        self.assertEqual(hold(counter, 130, 0.65)["reps"], 0)

    def test_rest_at_top_cannot_legitimize_an_implausibly_fast_cycle(self):
        counter = RepCounter()
        for index in range(30):
            counter.update(frame(170), now=index * 0.1)
        for now, angle in ((3.0, 90), (3.08, 90), (3.16, 170), (3.24, 170)):
            result = counter.update(frame(angle), now=now)
        self.assertEqual(result["reps"], 0)

    def test_unreliable_far_body_does_not_veto_clear_near_side(self):
        pose = frame(170)
        pose["landmarks"]["right_hip"]["y"] = 0.72
        pose["landmarks"]["right_hip"]["visibility"] = 0.6
        self.assertTrue(RepCounter().update(pose, now=0)["form_valid"])
        pose["landmarks"]["right_hip"]["visibility"] = 0.99
        self.assertFalse(RepCounter().update(pose, now=0)["form_valid"])


class MaxSetContinuityTests(ApiCase):
    def test_reps_with_brief_occlusion_renew_deadline_and_score_once(self):
        self.register()
        session_id = self.start("max_set")
        with self.websocket(session_id) as socket:
            for rep in range(1, 9):
                for angle in (170, 170, 140, 120, 100, 95, None, 130, 160, 170):
                    self.clock.advance(0.08)
                    pose = {"aspect_ratio": 1, "landmarks": None} if angle is None else far_arm_pose(angle, min(170, angle + 30))
                    socket.send_json(wire(pose, self.sequence))
                    self.sequence += 1
                    result = socket.receive_json()
                    self.assertEqual(result["type"], "workout_update")
                self.assertEqual(result["rep_count"], rep)
                self.assertEqual(result["remaining_ms"], 5000)
                self.assertEqual(result["measured_side"], "left")
            finished = self.post(f"/api/workouts/{session_id}/finish").json()
            self.assertEqual((finished["status"], finished["rep_count"], finished["xp_earned"]),
                             ("completed", 8, 80))
            self.assertEqual(self.post(f"/api/workouts/{session_id}/finish").json(), finished)

    def test_partial_movement_does_not_extend_deadline(self):
        self.register()
        session_id = self.start("max_set")
        with self.websocket(session_id) as socket:
            self.assertEqual(self.rep(socket)["rep_count"], 1)
            deadline = self.app.state.manager.runtimes[session_id].deadline_mono
            while self.clock.monotonic() < deadline:
                result = self.pose(socket, 130, step=0.08)
            self.assertEqual((result["type"], result["status"], result["rep_count"]),
                             ("workout_result", "completed", 1))
            self.assertEqual(result["xp_earned"], 10)
