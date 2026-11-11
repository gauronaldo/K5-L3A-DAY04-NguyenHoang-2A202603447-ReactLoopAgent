import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run_agent
from bonus.tools import BonusTools
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


class UnreadReferenceTests(unittest.TestCase):
    def test_linked_incident_triggers_follow_up(self):
        fake = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            final('Xem https://stspg.io/7pwv28hvkmz8'),
            tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Xem https://stspg.io/7pwv28hvkmz8 và https://stspg.io/pjgptg3cfc6n'),
        ])
        result = run_agent('Điều tra h02n9572mx9y', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        nudges = [x for x in result['trace'] if x['event'] == 'validation_unread_reference']
        self.assertEqual(nudges[0]['references'][0]['incident_id'], 'xr3myzj7ms51')
        self.assertEqual(len({x['step'] for x in result['trace'] if x['event'] == 'tool'}), 2)

    def test_reference_nudge_happens_once(self):
        fake = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            final('Xem https://stspg.io/7pwv28hvkmz8'),
            final('Không cần đọc thêm. https://stspg.io/7pwv28hvkmz8'),
        ])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=6)['status'], 'completed')

    def test_reference_nudge_skipped_without_budget(self):
        fake = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            final('Xem https://stspg.io/7pwv28hvkmz8'),
        ])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=2)['status'], 'completed')


class RetryBudgetTests(unittest.TestCase):
    def test_persistent_429_is_blocked_after_budget(self):
        calls = [tool_call(str(i), 'get_vercel_status', '{}') for i in range(4)]
        fake = FakeProvider(calls + [final('Không xác minh được Vercel.')])
        result = run_agent('x', fake, BonusTools(scenario='rate_limit_always'), max_steps=8)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(sum(x['event'] == 'tool' for x in result['trace']), 3)
        blocked = [x for x in result['trace'] if x['event'] == 'tool_blocked']
        self.assertEqual(blocked[0]['result']['error'], 'RETRY_BUDGET_EXHAUSTED')
        self.assertEqual(json.loads(fake.histories[4][-1]['content'])['error'], 'RETRY_BUDGET_EXHAUSTED')

    def test_unretried_429_gets_one_retry_prompt(self):
        fake = FakeProvider([tool_call('1', 'get_vercel_status', '{}'), final('Vercel bị rate limit.'),
                             tool_call('2', 'get_vercel_status', '{}'), final('Vercel operational.')])
        result = run_agent('x', fake, BonusTools(scenario='rate_limit_once'), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any(x['event'] == 'validation_unretried_rate_limit' for x in result['trace']))
        self.assertEqual(json.loads(fake.histories[3][-1]['content'])['provider'], 'vercel')


if __name__ == '__main__':
    unittest.main()
