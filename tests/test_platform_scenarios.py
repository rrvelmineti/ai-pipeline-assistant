"""Scenarios A–F from the pilot plan, end to end through the HTTP API. Synthetic data; no AI calls."""
import unittest

from claims_platform.scenarios import ai_unavailable, run_all

from _platform_env import PASSWORD, Platform


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with ai_unavailable(), Platform(export_batch_size=500) as p:
            cls.results, cls.ctx = run_all(p.client, PASSWORD, PASSWORD)

    def test_every_scenario_check_passes(self):
        for scenario in self.results["scenarios"]:
            for check in scenario["checks"]:
                with self.subTest(scenario=scenario["scenario"], check=check["id"]):
                    self.assertTrue(check["passed"], f"{check['criterion']}: {check['actual']}")

    def test_all_six_scenarios_ran(self):
        self.assertEqual([s["scenario"] for s in self.results["scenarios"]], list("ABCDEF"))
        self.assertGreaterEqual(self.results["checks_total"], 45)

    def test_planted_error_recall(self):
        self.assertEqual(self.results["planted_error_recall"],
                         {"planted": 52, "caught": 52, "missed": 0, "false_alarms": 0, "rows_checked": 2000})

    def test_kpis_carry_sample_sizes_and_no_invented_baseline(self):
        kpis = {k["name"]: k for k in self.results["portfolio_kpis"]}
        self.assertIn("First-pass acceptance rate", kpis)
        for k in kpis.values():
            self.assertIn("n", k)
            self.assertTrue(k["definition"])


if __name__ == "__main__":
    unittest.main()
