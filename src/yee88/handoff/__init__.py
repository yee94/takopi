"""Handoff backends for transferring session context to chat platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings import TakopiSettings


@dataclass(frozen=True)
class HandoffResult:
    """Result of a handoff operation."""

    success: bool
    thread_id: int | None
    url: str | None = None


@dataclass
class SessionContext:
    """Session context for handoff."""

    session_id: str
    project: str
    messages: list[dict]


class HandoffBackend(ABC):
    """Abstract base class for handoff backends.

    Each transport implements this to support session handoff
    from CLI to chat platform.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name."""
        ...

    @abstractmethod
    async def handoff(
        self,
        *,
        context: SessionContext,
        config_path: Path,
    ) -> HandoffResult:
        """Create a topic/thread and send session context.

        Args:
            context: Session context including messages
            config_path: Path to config file

        Returns:
            HandoffResult with success status and thread info
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend is configured and available."""
        ...

    @abstractmethod
    def format_messages(self, messages: list[dict], session_id: str, project: str | None) -> str:
        """Format messages for the platform."""
        ...
