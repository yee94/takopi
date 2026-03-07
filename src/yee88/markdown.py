from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from .model import Action, ActionEvent, StartedEvent, TakopiEvent
from .progress import ProgressState
from .transport import RenderedMessage
from .utils.paths import relativize_path

STATUS = {"running": "▸", "update": "↻", "done": "✓", "fail": "✗"}
FINAL_STATUS = {"done": "✅", "error": "❌", "cancelled": "⏹"}
PROGRESS_EMOJI = {
    "starting": "⏳",
    "working": "⏳",
    "queued": "⏳",
    "cancelled": "⏹",
}
HEADER_SEP = " · "
HARD_BREAK = "  \n"
BLOCKQUOTE_PREFIX = "> "
CTX_EMOJI = "📂"

MAX_PROGRESS_CMD_LEN = 300
MAX_FILE_CHANGES_INLINE = 3

# Known abbreviations that should be uppercased in model display names.
_MODEL_ABBREVIATIONS = frozenset({"gpt", "llm", "ai", "api", "vl"})

# Patterns that start with a lowercase letter followed by digits (e.g. o1, o3, o4).
# These should keep their original casing.
_LOWERCASE_MODEL_RE = re.compile(r"^[a-z]\d")


def format_context_display(context_line: str | None) -> str | None:
    """Convert a raw context line to a display-friendly format for footers.

    Examples::

        "`ctx: notes @main`"  → "📂 notes @main"
        "`ctx: takopi`"       → "📂 takopi"
        None                  → None
    """
    if not context_line:
        return None
    # Strip backticks
    text = context_line.strip("`").strip()
    # Remove "ctx:" prefix
    if text.lower().startswith("ctx:"):
        text = text[4:].strip()
    if not text:
        return None
    return f"{CTX_EMOJI} {text}"


def extract_model_display_name(model_or_engine: str) -> str:
    """Extract a human-friendly display name from a model identifier.

    Examples::

        "bailian/minimax-2.5"  → "Minimax 2.5"
        "gpt-4.1-mini"         → "GPT 4.1 Mini"
        "anthropic/claude-4-opus" → "Claude 4 Opus"
        "o4-mini"              → "o4 Mini"
    """
    if not model_or_engine:
        return ""
    # Take the last segment of a slash-separated path
    name = model_or_engine.rsplit("/", 1)[-1]
    # Replace hyphens with spaces
    name = name.replace("-", " ")
    words = name.split()
    result: list[str] = []
    for word in words:
        lower = word.lower()
        if lower in _MODEL_ABBREVIATIONS:
            result.append(word.upper())
        elif _LOWERCASE_MODEL_RE.match(word):
            # Keep original casing for patterns like "o4", "o3"
            result.append(word)
        else:
            result.append(word.title())
    return " ".join(result)


@dataclass(frozen=True, slots=True)
class MarkdownParts:
    header: str
    body: str | None = None
    footer: str | None = None


def assemble_markdown_parts(parts: MarkdownParts) -> str:
    return "\n\n".join(
        chunk for chunk in (parts.header, parts.body, parts.footer) if chunk
    )


def format_changed_file_path(path: str, *, base_dir: Path | None = None) -> str:
    return f"`{relativize_path(path, base_dir=base_dir)}`"


def format_elapsed(elapsed_s: float) -> str:
    total = max(0, int(elapsed_s))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def format_header(
    elapsed_s: float, item: int | None, *, label: str, engine: str
) -> str:
    elapsed = format_elapsed(elapsed_s)
    parts = [label, engine]
    parts.append(elapsed)
    if item is not None:
        parts.append(f"step {item}")
    return HEADER_SEP.join(parts)


def _format_progress_status(
    state: ProgressState,
    *,
    elapsed_s: float,
    label: str,
) -> str:
    """Build a blockquote status block for progress (in-flight) messages.

    Format::

        > ⏳ 3s · step 2 · Codex
        > 📂 takopi @master
    """
    # Strip backtick wrapping from label (e.g. "`cancelled`" → "cancelled")
    clean_label = label.strip("`").strip()
    emoji = PROGRESS_EMOJI.get(clean_label, "⏳")

    elapsed = format_elapsed(elapsed_s)
    parts: list[str] = []
    # For "queued" show the label instead of elapsed time
    if clean_label == "queued":
        parts.append(clean_label)
    else:
        parts.append(elapsed)
    step = state.action_count or None
    if step is not None:
        parts.append(f"step {step}")
    display_engine = extract_model_display_name(state.model or state.engine)
    parts.append(display_engine)
    status_line = f"{emoji} {HEADER_SEP.join(parts)}"

    lines: list[str] = [status_line]
    # Context and meta lines
    ctx_parts: list[str] = []
    ctx_display = format_context_display(state.context_line)
    if ctx_display:
        ctx_parts.append(ctx_display)
    if ctx_parts:
        lines.append(HEADER_SEP.join(ctx_parts))
    return "\n".join(f"{BLOCKQUOTE_PREFIX}{line}" for line in lines)


def shorten(text: str, width: int | None) -> str:
    if width is None:
        return text
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    return textwrap.shorten(text, width=width, placeholder="…")


def action_status(action: Action, *, completed: bool, ok: bool | None = None) -> str:
    if not completed:
        return STATUS["running"]
    if ok is not None:
        return STATUS["done"] if ok else STATUS["fail"]
    detail = action.detail or {}
    exit_code = detail.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return STATUS["fail"]
    return STATUS["done"]


def action_suffix(action: Action) -> str:
    detail = action.detail or {}
    exit_code = detail.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return f" (exit {exit_code})"
    return ""


def format_file_change_title(action: Action, *, command_width: int | None) -> str:
    title = str(action.title or "")
    detail = action.detail or {}

    changes = detail.get("changes")
    if isinstance(changes, list) and changes:
        rendered: list[str] = []
        for raw in changes:
            path: str | None
            kind: str | None
            if isinstance(raw, dict):
                path = raw.get("path")
                kind = raw.get("kind")
            else:
                path = getattr(raw, "path", None)
                kind = getattr(raw, "kind", None)
            if not isinstance(path, str) or not path:
                continue
            verb = kind if isinstance(kind, str) and kind else "update"
            rendered.append(f"{verb} {format_changed_file_path(path)}")

        if rendered:
            if len(rendered) > MAX_FILE_CHANGES_INLINE:
                remaining = len(rendered) - MAX_FILE_CHANGES_INLINE
                rendered = rendered[:MAX_FILE_CHANGES_INLINE] + [f"…({remaining} more)"]
            inline = shorten(", ".join(rendered), command_width)
            return f"files: {inline}"

    fallback = title
    relativized = relativize_path(fallback)
    was_relativized = relativized != fallback
    if was_relativized:
        fallback = relativized
    if (
        fallback
        and not (fallback.startswith("`") and fallback.endswith("`"))
        and (was_relativized or os.sep in fallback or "/" in fallback)
    ):
        fallback = f"`{fallback}`"
    return f"files: {shorten(fallback, command_width)}"


def format_action_title(action: Action, *, command_width: int | None) -> str:
    title = str(action.title or "")
    kind = action.kind
    if kind == "command":
        title = shorten(title, command_width)
        return f"`{title}`"
    if kind == "tool":
        title = shorten(title, command_width)
        return f"tool: {title}"
    if kind == "web_search":
        title = shorten(title, command_width)
        return f"searched: {title}"
    if kind == "subagent":
        title = shorten(title, command_width)
        return f"subagent: {title}"
    if kind == "file_change":
        return format_file_change_title(action, command_width=command_width)
    if kind in {"note", "warning"}:
        return shorten(title, command_width)
    return shorten(title, command_width)


def format_action_line(
    action: Action,
    phase: str,
    ok: bool | None,
    *,
    command_width: int | None,
) -> str:
    if phase != "completed":
        status = STATUS["update"] if phase == "updated" else STATUS["running"]
        return f"{status} {format_action_title(action, command_width=command_width)}"
    status = action_status(action, completed=True, ok=ok)
    suffix = action_suffix(action)
    return (
        f"{status} {format_action_title(action, command_width=command_width)}{suffix}"
    )


def render_event_cli(event: TakopiEvent) -> list[str]:
    from .model import TextFinishedEvent

    match event:
        case StartedEvent(engine=engine):
            return [str(engine)]
        case ActionEvent() as action_event:
            action = action_event.action
            if action.kind == "turn":
                return []
            return [
                format_action_line(
                    action_event.action,
                    action_event.phase,
                    action_event.ok,
                    command_width=MAX_PROGRESS_CMD_LEN,
                )
            ]
        case TextFinishedEvent(engine=engine, text=text):
            preview = shorten(text, MAX_PROGRESS_CMD_LEN)
            return [f"text_finished ({engine}): {preview}"]
        case _:
            return []


class MarkdownFormatter:
    def __init__(
        self,
        *,
        max_actions: int = 5,
        command_width: int | None = MAX_PROGRESS_CMD_LEN,
    ) -> None:
        self.max_actions = max(0, int(max_actions))
        self.command_width = command_width

    def render_progress_parts(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        label: str = "working",
    ) -> MarkdownParts:
        body_lines: list[str] = []
        # Show intermediate text segments from agent reasoning
        for segment in state.text_segments:
            body_lines.append(segment)
        # Show current streaming text (live preview)
        if state.streaming_text:
            body_lines.append(state.streaming_text)
        # Show action lines (tool calls)
        body_lines.extend(self._format_actions(state))
        body = self._assemble_body(body_lines)
        # Blockquote status footer
        footer = _format_progress_status(state, elapsed_s=elapsed_s, label=label)
        if body is None:
            # No actions/text – status block is the only content
            return MarkdownParts(header=footer)
        return MarkdownParts(header="", body=body, footer=footer)

    def render_final_parts(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        status: str,
        answer: str,
    ) -> MarkdownParts:
        answer = (answer or "").strip()
        body = answer if answer else None
        footer = self._format_final_footer(state, elapsed_s=elapsed_s, status=status)
        if body is None:
            # No answer – footer is the only content
            return MarkdownParts(header=footer)
        return MarkdownParts(header="", body=body, footer=footer)

    def _format_final_footer(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        status: str,
    ) -> str:
        """Build compact footer for final messages, rendered as blockquote.

        Format::

            > ✅ 13s · step 12 · Claude 4.6 Opus
            > 📂 takopi @master
        """
        emoji = FINAL_STATUS.get(status, FINAL_STATUS["done"])
        elapsed = format_elapsed(elapsed_s)
        parts: list[str] = [elapsed]
        step = state.action_count or None
        if step is not None:
            parts.append(f"step {step}")
        # Prefer model name over engine id for display;
        # extract a human-friendly display name from the model path.
        display_engine = extract_model_display_name(state.model or state.engine)
        parts.append(display_engine)
        status_line = f"{emoji} {HEADER_SEP.join(parts)}"

        lines: list[str] = [status_line]
        # Context line (project + branch) and resume hint
        ctx_parts: list[str] = []
        ctx_display = format_context_display(state.context_line)
        if ctx_display:
            ctx_parts.append(ctx_display)
        if ctx_parts:
            lines.append(HEADER_SEP.join(ctx_parts))
        return "\n".join(f"{BLOCKQUOTE_PREFIX}{line}" for line in lines)

    def _format_actions(self, state: ProgressState) -> list[str]:
        actions = list(state.actions)
        actions = [] if self.max_actions == 0 else actions[-self.max_actions :]
        return [
            format_action_line(
                action_state.action,
                action_state.display_phase,
                action_state.ok,
                command_width=self.command_width,
            )
            for action_state in actions
        ]

    @staticmethod
    def _assemble_body(lines: list[str]) -> str | None:
        if not lines:
            return None
        return HARD_BREAK.join(lines)


class MarkdownPresenter:
    def __init__(self, *, formatter: MarkdownFormatter | None = None) -> None:
        self._formatter = formatter or MarkdownFormatter()

    def render_progress(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        label: str = "working",
    ) -> RenderedMessage:
        parts = self._formatter.render_progress_parts(
            state, elapsed_s=elapsed_s, label=label
        )
        return RenderedMessage(text=assemble_markdown_parts(parts))

    def render_final(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        status: str,
        answer: str,
    ) -> RenderedMessage:
        parts = self._formatter.render_final_parts(
            state, elapsed_s=elapsed_s, status=status, answer=answer
        )
        return RenderedMessage(text=assemble_markdown_parts(parts))
