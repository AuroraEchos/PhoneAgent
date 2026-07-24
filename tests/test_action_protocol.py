from __future__ import annotations

import unittest

from phoneagent.actions import ActionParseError, parse_action
from phoneagent.model import ModelClient, ModelProtocolError, ModelResponseParser


class ActionProtocolTests(unittest.TestCase):
    def test_canonical_action_envelope(self) -> None:
        action = parse_action(
            '<think>点击按钮</think><answer>do(action="Tap", element=[500, 300])</answer>'
        )
        self.assertEqual(action["action"], "Tap")
        self.assertEqual(action["element"], [500, 300])

    def test_finish_call(self) -> None:
        action = parse_action('finish(message="done", success=True)')
        self.assertEqual(action["_metadata"], "finish")
        self.assertTrue(action["success"])

    def test_rejects_json_and_code_fence(self) -> None:
        with self.assertRaises(ActionParseError):
            parse_action('{"action":"Tap","element":[1,2]}')
        with self.assertRaises(ActionParseError):
            parse_action('```python\ndo(action="Back")\n```')

    def test_rejects_multiple_or_incomplete_calls(self) -> None:
        with self.assertRaises(ActionParseError):
            parse_action('do(action="Back") do(action="Home")')
        with self.assertRaises(ActionParseError):
            parse_action('do(action="Type", text="unterminated)')

    def test_model_parser_uses_narrow_protocol(self) -> None:
        thinking, action = ModelResponseParser.parse(
            '<think>当前是首页</think><answer>do(action="Back")</answer>'
        )
        self.assertEqual(thinking, "当前是首页")
        self.assertEqual(action, 'do(action="Back")')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('```json\n{"action":"Back"}\n```')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('<answer>do(action="Back")')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('先返回上一页 do(action="Back")')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse("")
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse("<answer></answer>")

    def test_protocol_errors_are_not_retried_as_transport_failures(self) -> None:
        self.assertFalse(ModelClient._is_retryable(ModelProtocolError("invalid envelope")))


if __name__ == "__main__":
    unittest.main()
