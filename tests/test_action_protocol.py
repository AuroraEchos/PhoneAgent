from __future__ import annotations

import unittest

from phoneagent.actions import ActionParseError, parse_action
from phoneagent.model import ModelClient, ModelProtocolError, ModelResponse, ModelResponseParser


class ActionProtocolTests(unittest.TestCase):
    def test_canonical_terminal_action(self) -> None:
        thinking, action_text = ModelResponseParser.parse('do(action="Tap", element=[500, 300])')
        action = parse_action(action_text)
        self.assertEqual(thinking, "")
        self.assertEqual(action["action"], "Tap")
        self.assertEqual(action["element"], [500, 300])

    def test_finish_call(self) -> None:
        action = parse_action('finish(message="done", success=True)')
        self.assertEqual(action["_metadata"], "finish")
        self.assertTrue(action["success"])

    def test_finish_call_accepts_literal_newlines_in_message(self) -> None:
        action = parse_action(
            'finish(message="任务完成！\n\n当前显示的是 WLAN 设置页面。", success=True)'
        )
        self.assertEqual(action["_metadata"], "finish")
        self.assertEqual(action["message"], "任务完成！\n\n当前显示的是 WLAN 设置页面。")
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

    def test_normalizes_provider_point_markers(self) -> None:
        samples = (
            'do(action="Tap", element=[<point>250 126</point>])',
            'do(action="Tap", element=<point_2d>(250, 126)</point_2d>)',
            'do(action="Tap", element="<point>250,126</point>")',
            'do(action="Tap", element=<|point_start|>(250,126)<|point_end|>)',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                action = parse_action(sample)
                self.assertEqual(action["element"], [250, 126])

    def test_normalizes_provider_swipe_points_and_coordinate_objects(self) -> None:
        swipe = parse_action(
            'do(action="Swipe", start=[<point>500 800</point>], end=[<point>500 200</point>])'
        )
        self.assertEqual(swipe["start"], [500, 800])
        self.assertEqual(swipe["end"], [500, 200])

        tap = parse_action('do(action="Tap", element={"x": 250, "y": 126})')
        self.assertEqual(tap["element"], [250, 126])

    def test_provider_coordinate_compatibility_remains_strict(self) -> None:
        invalid_samples = (
            'do(action="Tap", element=[<point>1000 126</point>])',
            'do(action="Tap", element=[<point>__import__("os") 126</point>])',
            'do(action="Tap", element=[<box>10 20 30 40</box>])',
            'do(action="Tap", element=[<point>10 20</point>, <point>30 40</point>])',
            'do(action="Tap", element={"x": 250, "y": 126, "z": 1})',
        )
        for sample in invalid_samples:
            with self.subTest(sample=sample), self.assertRaises(ActionParseError):
                parse_action(sample)

    def test_provider_marker_text_inside_string_is_not_rewritten(self) -> None:
        action = parse_action('do(action="Type", text="保留 element=<point>10 20</point> 原文")')
        self.assertEqual(action["text"], "保留 element=<point>10 20</point> 原文")

    def test_model_parser_uses_terminal_action_protocol(self) -> None:
        thinking, action = ModelResponseParser.parse('do(action="Back")')
        self.assertEqual(thinking, "")
        self.assertEqual(action, 'do(action="Back")')

        thinking, action = ModelResponseParser.parse(
            "用户要求打开设置，找到无线网络界面。\n\n"
            "我应该使用 Launch 功能来打开设置应用。\n"
            'do(action="Launch", app="设置")'
        )
        self.assertEqual(
            thinking,
            "用户要求打开设置，找到无线网络界面。\n\n我应该使用 Launch 功能来打开设置应用。",
        )
        self.assertEqual(action, 'do(action="Launch", app="设置")')
        self.assertEqual(parse_action(action)["action"], "Launch")

        thinking, action = ModelResponseParser.parse(
            '当前页面不是订单页面，需要返回。</think>\ndo(action="Back")'
        )
        self.assertEqual(thinking, "当前页面不是订单页面，需要返回。</think>")
        self.assertEqual(action, 'do(action="Back")')

        thinking, action = ModelResponseParser.parse(
            '当前页面展示了文本“undo(操作)”，需要返回上一页。\ndo(action="Back")'
        )
        self.assertIn("undo(操作)", thinking)
        self.assertEqual(parse_action(action)["action"], "Back")

    def test_model_parser_requires_one_terminal_action_call(self) -> None:
        invalid_samples = (
            '<action>do(action="Back")',
            'do(action="Back")</action>',
            "<action></action>",
            'do(action="Back") trailing',
            'do(action="Back")\ndo(action="Home")',
            '先考虑 do(action="Home")，最终返回。\ndo(action="Back")',
            '```python\ndo(action="Back")\n```',
            '<answer>do(action="Back")</answer>',
            'do(action="Back"',
        )
        for sample in invalid_samples:
            with self.subTest(sample=sample), self.assertRaises(ModelProtocolError):
                ModelResponseParser.parse(sample)

    def test_action_parser_only_accepts_extracted_action_text(self) -> None:
        with self.assertRaises(ActionParseError):
            parse_action('<action>do(action="Back")</action>')

    def test_assistant_history_serializes_only_the_action(self) -> None:
        response = ModelResponse(
            thinking="不会回填到模型上下文",
            action='do(action="Back")',
            raw_content='分析内容\ndo(action="Back")',
        )
        self.assertEqual(
            response.to_assistant_message_content(),
            'do(action="Back")',
        )

    def test_malformed_action_protocol_is_rejected(self) -> None:
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('```json\n{"action":"Back"}\n```')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse("")

    def test_terminal_protocol_handles_nested_call_text_safely(self) -> None:
        thinking, action = ModelResponseParser.parse(
            '输入一段包含函数名称的文本。\ndo(action="Type", text="保留 finish(example) 原文")'
        )
        self.assertEqual(thinking, "输入一段包含函数名称的文本。")
        self.assertEqual(parse_action(action)["text"], "保留 finish(example) 原文")

    def test_terminal_protocol_rejects_extra_or_incomplete_actions(self) -> None:
        invalid_samples = (
            'do(action="Back") do(action="Home")',
            'do(action="Back") 然后继续',
            'do(action="Back"',
        )
        for sample in invalid_samples:
            with self.subTest(sample=sample), self.assertRaises(ModelProtocolError):
                ModelResponseParser.parse(sample)

    def test_protocol_errors_are_not_retried_as_transport_failures(self) -> None:
        self.assertFalse(ModelClient._is_retryable(ModelProtocolError("invalid action")))


if __name__ == "__main__":
    unittest.main()
