import unittest
from benchmarks.metrics import percentile, score_trial, summarize


class BenchmarkMetricsTests(unittest.TestCase):
    def test_percentiles_empty_and_interpolated(self):
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(percentile([1, 2, 3, 4, 5], 95), 4.8)

    def test_score_requires_actual_correct_query_and_final_value(self):
        trial = {'initial': '0907', 'target': '0906', 'target_value': 120,
                 'initial_value': 0, 'condition': 'steered', 'error': None,
                 'emission_at_ns': 20,
                 'calls': [{'selection': '0907', 'value': 0, 'completed_at_ns': 10},
                           {'selection': '0906', 'value': 120, 'completed_at_ns': 30, 'after_guidance': True}],
                 'emitted': True, 'final': {'selection': '0906', 'value': 120}}
        score = score_trial(trial)
        self.assertTrue(score['revised_target_success'])
        self.assertTrue(score['adopted'])
        self.assertEqual(score['wrong_calls_after_boundary'], 0)
        trial['calls'] = trial['calls'][:1]
        self.assertFalse(score_trial(trial)['revised_target_success'])
        trial['calls'].append({'selection': '0906', 'value': 120, 'completed_at_ns': 30, 'after_guidance': True})
        trial['final']['value'] = 999
        self.assertFalse(score_trial(trial)['revised_target_success'])
        trial['error'] = 'timeout'
        self.assertFalse(score_trial(trial)['adopted'])

    def test_empty_summary_and_failure_denominator(self):
        self.assertEqual(summarize([])['attempts'], 0)
        result = summarize([{'success': True, 'latency_ms': 10},
                            {'success': False, 'latency_ms': None}])
        self.assertEqual(result['success_rate'], 0.5)
        self.assertEqual(result['latency_samples'], 1)
        self.assertEqual(result['latency_p95_ms'], 10)
