from __future__ import annotations

import pytest

from phoneagent.actions import ActionHandler, ActionParseError, parse_action


def test_parse_wrapped_tap_action() -> None:
    action = parse_action(
        '<think>tap the visible button</think>'
        '<answer>do(action="Tap", element=[500, 250])</answer>'
    )
    assert action == {"_metadata": "do", "action": "Tap", "element": [500, 250]}


def test_parse_json_finish_action() -> None:
    action = parse_action('{"type":"finish","message":"done","success":true}')
    assert action["_metadata"] == "finish"
    assert action["message"] == "done"
    assert action["success"] is True


def test_parser_rejects_executable_python() -> None:
    with pytest.raises(ActionParseError):
        parse_action('do(action="Tap", element=__import__("os").system("id"))')


def test_coordinate_scaling_is_bounded() -> None:
    assert ActionHandler._relative_to_absolute([0, 0], 1080, 2400) == (0, 0)
    assert ActionHandler._relative_to_absolute([999, 999], 1080, 2400) == (1079, 2399)
    assert ActionHandler._relative_to_absolute([500, 500], 1080, 2400) == (540, 1201)
