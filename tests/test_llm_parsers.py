"""Tests for LLM response parsing."""

from gazefy.actions.action_types import ActionType
from gazefy.llm.parsers import parse_actions


def test_parse_valid_actions():
    response = '{"actions": [{"type": "click", "target": "btn_01"}, {"type": "type_text", "target": "inp_01", "text": "hello"}]}'
    actions = parse_actions(response)
    assert len(actions) == 2
    assert actions[0].type == ActionType.CLICK
    assert actions[0].target_element_id == "btn_01"
    assert actions[1].type == ActionType.TYPE_TEXT
    assert actions[1].text == "hello"


def test_parse_markdown_wrapped():
    response = """```json
{"actions": [{"type": "click", "target": "btn_01"}]}
```"""
    actions = parse_actions(response)
    assert len(actions) == 1
    assert actions[0].type == ActionType.CLICK


def test_parse_empty_actions():
    response = '{"actions": []}'
    assert parse_actions(response) == []


def test_parse_invalid_json():
    assert parse_actions("this is not json") == []


def test_parse_unknown_action_type_skipped():
    response = '{"actions": [{"type": "fly_away", "target": "x"}, {"type": "click", "target": "btn"}]}'
    actions = parse_actions(response)
    assert len(actions) == 1
    assert actions[0].type == ActionType.CLICK


def test_parse_hotkey():
    response = '{"actions": [{"type": "hotkey", "keys": ["ctrl", "c"]}]}'
    actions = parse_actions(response)
    assert len(actions) == 1
    assert actions[0].keys == ("ctrl", "c")


def test_parse_scroll():
    response = '{"actions": [{"type": "scroll", "target": "list_01", "scroll": -3}]}'
    actions = parse_actions(response)
    assert len(actions) == 1
    assert actions[0].scroll_amount == -3


def test_parse_no_actions_key():
    response = '{"result": "ok"}'
    assert parse_actions(response) == []
