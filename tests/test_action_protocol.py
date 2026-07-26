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
            'do(action="Swipe", start=[<point>500 800</point>], '
            'end=[<point>500 200</point>])'
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
        action = parse_action(
            'do(action="Type", text="保留 element=<point>10 20</point> 原文")'
        )
        self.assertEqual(action["text"], "保留 element=<point>10 20</point> 原文")

    def test_model_parser_uses_narrow_protocol(self) -> None:
        thinking, action = ModelResponseParser.parse(
            '<think>当前是首页</think><answer>do(action="Back")</answer>'
        )
        self.assertEqual(thinking, "当前是首页")
        self.assertEqual(action, 'do(action="Back")')

        thinking, action = ModelResponseParser.parse(
            "用户要求打开设置，找到无线网络界面。\n\n"
            "我应该使用 Launch 功能来打开设置应用。\n"
            'do(action="Launch", app="设置")'
        )
        self.assertEqual(
            thinking,
            "用户要求打开设置，找到无线网络界面。\n\n"
            "我应该使用 Launch 功能来打开设置应用。",
        )
        self.assertEqual(action, 'do(action="Launch", app="设置")')
        self.assertEqual(parse_action(action)["action"], "Launch")

        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('```json\n{"action":"Back"}\n```')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse('<answer>do(action="Back")')
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse("")
        with self.assertRaises(ModelProtocolError):
            ModelResponseParser.parse("<answer></answer>")

    def test_compatibility_response_still_rejects_extra_or_incomplete_actions(self) -> None:
        _, multiple = ModelResponseParser.parse(
            '先返回上一页 do(action="Back") do(action="Home")'
        )
        with self.assertRaises(ActionParseError):
            parse_action(multiple)

        _, trailing = ModelResponseParser.parse('先返回上一页 do(action="Back") 然后继续')
        with self.assertRaises(ActionParseError):
            parse_action(trailing)

        _, incomplete = ModelResponseParser.parse('返回上一页 do(action="Back"')
        with self.assertRaises(ActionParseError):
            parse_action(incomplete)

    def test_protocol_errors_are_not_retried_as_transport_failures(self) -> None:
        self.assertFalse(ModelClient._is_retryable(ModelProtocolError("invalid envelope")))


if __name__ == "__main__":
    unittest.main()
