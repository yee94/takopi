"""Topic management backends for yee88.

Provides a pluggable architecture for creating and managing topics/threads
across different transport backends (Telegram, Discord, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import RunContext


@dataclass(frozen=True)
class TopicInfo:
    """Information about a created topic/thread."""

    thread_id: int
    title: str
    url: str | None = None  # Optional link to the topic


class TopicBackend(ABC):
    """Abstract base class for topic management backends.

    Each transport (Telegram, Discord, etc.) implements this interface
to provide topic/thread creation and management capabilities.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name (e.g., 'telegram', 'discord')."""
        ...

    @abstractmethod
    async def create_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> TopicInfo | None:
        """Create a new topic/thread bound to project/branch.

        Args:
            project: Project alias
            branch: Optional branch name
            config_path: Path to config file for state storage

        Returns:
            TopicInfo on success, None on failure
        """
        ...

    @abstractmethod
    async def delete_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> bool:
        """Delete/unbind a topic from project/branch.

        Args:
            project: Project alias
            branch: Optional branch name
            config_path: Path to config file for state storage

        Returns:
            True if topic was found and deleted, False otherwise
        """
        ...

    @abstractmethod
    async def list_topics(
        self,
        *,
        config_path: Path,
    ) -> list[TopicInfo]:
        """List all managed topics.

        Args:
            config_path: Path to config file for state storage

        Returns:
            List of TopicInfo objects
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is properly configured and available.

        Returns:
            True if backend can be used, False otherwise
        """
        ...
