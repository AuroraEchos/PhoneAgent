from __future__ import annotations

import unittest

from phoneagent.model.context import (
    compact_for_protocol_recovery,
    prepare_protocol_recovery,
    trim_context,
)


class ModelContextTests(unittest.TestCase):
    def test_trim_keeps_system_recent_pairs_and_pending_user(self) -> None:
        messages = [{"role": "system", "content": "s"}]
        for index in range(4):
            messages.extend(
                [
                    {"role": "user", "content": f"u{index}"},
                    {"role": "assistant", "content": f"a{index}"},
                ]
            )
        messages.append({"role": "user", "content": "current"})
        trim_context(messages, turns=2)
        self.assertEqual([m["content"] for m in messages], ["s", "u2", "a2", "u3", "a3", "current"])

    def test_protocol_recovery_discards_pending_turn(self) -> None:
        messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "bad"},
        ]
        text = prepare_protocol_recovery(messages, reason="invalid", app_context={})
        self.assertEqual(len(messages), 3)
        self.assertIn("exactly one valid action", text)
        compact_for_protocol_recovery(messages)
        self.assertEqual(len(messages), 3)


if __name__ == "__main__":
    unittest.main()
