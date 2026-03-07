"""Tests for the question tool support."""

from __future__ import annotations

import json

import pytest

from yee88.model import ActionEvent, Action, ResumeToken
from yee88.runners import tool_actions
from yee88.runners.opencode import (
    OpenCodeStreamState,
    ENGINE,
    translate_opencode_event,
)
from yee88.schemas import opencode as opencode_schema
from yee88.telegram.commands.question import (
    QUESTION_CALLBACK_PREFIX,
    build_question_callback_data,
    build_question_keyboard,
    format_question_answer,
    format_question_message,
    parse_question_callback_data,
)
from yee88.utils.paths import reset_run_base_dir, set_run_base_dir


# ---------------------------------------------------------------------------
# tool_actions: question tool recognition
# ---------------------------------------------------------------------------


class TestToolActionsQuestion:
    def test_question_tool_recognized(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "question",
                {"questions": [{"question": "Pick a color", "header": "Color"}]},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert title == "Color"

    def test_question_tool_with_long_header_truncated(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "question",
                {"questions": [{"question": "x", "header": "A" * 100}]},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert len(title) == 60

    def test_question_tool_falls_back_to_question_text(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "question",
                {"questions": [{"question": "What framework?"}]},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert title == "What framework?"

    def test_question_tool_empty_questions(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "question",
                {"questions": []},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert title == "ask user"

    def test_question_tool_no_questions_key(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "question",
                {},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert title == "ask user"

    def test_askuserquestion_also_recognized(self) -> None:
        token = set_run_base_dir(None)
        try:
            kind, title = tool_actions.tool_kind_and_title(
                "askuserquestion",
                {},
                path_keys=("path",),
            )
        finally:
            reset_run_base_dir(token)
        assert kind == "question"
        assert title == "ask user"


# ---------------------------------------------------------------------------
# opencode runner: question tool_use event translation
# ---------------------------------------------------------------------------


def _decode_event(payload: dict) -> opencode_schema.OpenCodeEvent:
    return opencode_schema.decode_event(json.dumps(payload).encode("utf-8"))


class TestOpenCodeQuestionEvent:
    def _make_question_tool_use(
        self, *, status: str = "pending"
    ) -> opencode_schema.OpenCodeEvent:
        return _decode_event(
            {
                "type": "tool_use",
                "sessionID": "ses_q1",
                "part": {
                    "id": "prt_q1",
                    "callID": "call_q1",
                    "tool": "question",
                    "state": {
                        "status": status,
                        "input": {
                            "questions": [
                                {
                                    "question": "Which framework?",
                                    "header": "Framework",
                                    "options": [
                                        {"label": "React", "description": "UI lib"},
                                        {"label": "Vue", "description": "Progressive"},
                                    ],
                                    "multiple": False,
                                    "custom": True,
                                }
                            ]
                        },
                    },
                },
            }
        )

    def test_question_pending_emits_started_action(self) -> None:
        state = OpenCodeStreamState()
        state.session_id = "ses_q1"
        state.emitted_started = True

        events = translate_opencode_event(
            self._make_question_tool_use(status="pending"),
            title="opencode",
            state=state,
        )

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ActionEvent)
        assert evt.phase == "started"
        assert evt.action.kind == "question"
        assert evt.action.title == "Framework"
        assert "questions" in evt.action.detail
        questions = evt.action.detail["questions"]
        assert len(questions) == 1
        assert questions[0]["question"] == "Which framework?"
        assert len(questions[0]["options"]) == 2

    def test_question_pending_stored_in_pending_actions(self) -> None:
        state = OpenCodeStreamState()
        state.session_id = "ses_q1"
        state.emitted_started = True

        translate_opencode_event(
            self._make_question_tool_use(status="pending"),
            title="opencode",
            state=state,
        )

        assert "call_q1" in state.pending_actions
        assert state.pending_actions["call_q1"].kind == "question"

    def test_question_completed_emits_completed_action(self) -> None:
        state = OpenCodeStreamState()
        state.session_id = "ses_q1"
        state.emitted_started = True

        events = translate_opencode_event(
            self._make_question_tool_use(status="completed"),
            title="opencode",
            state=state,
        )

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ActionEvent)
        assert evt.phase == "completed"
        assert evt.action.kind == "question"


# ---------------------------------------------------------------------------
# question.py: callback data encoding/decoding
# ---------------------------------------------------------------------------


class TestQuestionCallbackData:
    def test_build_and_parse_roundtrip(self) -> None:
        data = build_question_callback_data("call_abc", 2)
        parsed = parse_question_callback_data(data)
        assert parsed == ("call_abc", 2)

    def test_parse_invalid_prefix(self) -> None:
        assert parse_question_callback_data("yee88:cancel") is None

    def test_parse_missing_index(self) -> None:
        assert (
            parse_question_callback_data(f"{QUESTION_CALLBACK_PREFIX}call_abc") is None
        )

    def test_parse_non_numeric_index(self) -> None:
        assert (
            parse_question_callback_data(f"{QUESTION_CALLBACK_PREFIX}call_abc:xyz")
            is None
        )

    def test_callback_data_starts_with_prefix(self) -> None:
        data = build_question_callback_data("id1", 0)
        assert data.startswith(QUESTION_CALLBACK_PREFIX)


# ---------------------------------------------------------------------------
# question.py: message formatting
# ---------------------------------------------------------------------------


class TestFormatQuestionMessage:
    def test_single_question_with_options(self) -> None:
        questions = [
            {
                "question": "Pick a color",
                "header": "Color",
                "options": [
                    {"label": "Red", "description": "Warm"},
                    {"label": "Blue", "description": "Cool"},
                ],
            }
        ]
        text = format_question_message(questions)
        assert "Color" in text
        assert "Pick a color" in text
        assert "Red" in text
        assert "Blue" in text
        assert "Warm" in text

    def test_question_without_header(self) -> None:
        questions = [{"question": "Yes or no?", "options": []}]
        text = format_question_message(questions)
        assert "Yes or no?" in text

    def test_empty_questions(self) -> None:
        assert format_question_message([]) == ""


# ---------------------------------------------------------------------------
# question.py: keyboard building
# ---------------------------------------------------------------------------


class TestBuildQuestionKeyboard:
    def test_keyboard_has_option_buttons(self) -> None:
        questions = [
            {
                "question": "Pick",
                "options": [
                    {"label": "A"},
                    {"label": "B"},
                ],
                "custom": True,
            }
        ]
        kb = build_question_keyboard("call_1", questions)
        rows = kb["inline_keyboard"]
        # 2 option rows + 1 custom hint row
        assert len(rows) == 3
        assert rows[0][0]["text"] == "A"
        assert rows[1][0]["text"] == "B"
        assert "Type your own" in rows[2][0]["text"]

    def test_keyboard_no_custom_hint_when_disabled(self) -> None:
        questions = [
            {
                "question": "Pick",
                "options": [{"label": "A"}],
                "custom": False,
            }
        ]
        kb = build_question_keyboard("call_1", questions)
        rows = kb["inline_keyboard"]
        assert len(rows) == 1
        assert rows[0][0]["text"] == "A"

    def test_keyboard_empty_questions(self) -> None:
        kb = build_question_keyboard("call_1", [])
        assert kb["inline_keyboard"] == []

    def test_keyboard_callback_data_format(self) -> None:
        questions = [
            {
                "question": "Pick",
                "options": [{"label": "X"}],
            }
        ]
        kb = build_question_keyboard("call_1", questions)
        cb_data = kb["inline_keyboard"][0][0]["callback_data"]
        assert cb_data.startswith(QUESTION_CALLBACK_PREFIX)
        parsed = parse_question_callback_data(cb_data)
        assert parsed == ("call_1", 0)


# ---------------------------------------------------------------------------
# question.py: answer formatting
# ---------------------------------------------------------------------------


class TestFormatQuestionAnswer:
    def test_valid_option_index(self) -> None:
        questions = [
            {
                "question": "Pick",
                "options": [
                    {"label": "React"},
                    {"label": "Vue"},
                ],
            }
        ]
        assert format_question_answer(questions, 0) == "React"
        assert format_question_answer(questions, 1) == "Vue"

    def test_out_of_range_index(self) -> None:
        questions = [{"question": "Pick", "options": [{"label": "A"}]}]
        assert format_question_answer(questions, 5) == "Option 6"

    def test_empty_questions(self) -> None:
        assert format_question_answer([], 0) == ""
