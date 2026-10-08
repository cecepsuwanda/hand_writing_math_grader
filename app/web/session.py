"""Server-wide session state for the single local user: config + active topic."""

from __future__ import annotations

import threading

from app.config import AppConfig
from app.interfaces.topic_pack import TopicPack
from app.topics.registry import get_pack


class WebSession:
    """Active topic shared by every page; grading follows it for every run.

    ``explicit_topic_id`` stays ``None`` until the user picks a topic, so grading
    keeps resolving the pack from ``exam_schema.json`` first.
    """

    def __init__(self, config: AppConfig, *, topic_id: str | None = None) -> None:
        self._lock = threading.Lock()
        pack = get_pack(topic_id or config.grading.topic_id)
        self._config = self._with_topic(config, pack.id)
        self._explicit_topic_id = pack.id if topic_id else None

    @property
    def config(self) -> AppConfig:
        with self._lock:
            return self._config

    @property
    def topic_id(self) -> str:
        return self.config.grading.topic_id

    @property
    def explicit_topic_id(self) -> str | None:
        with self._lock:
            return self._explicit_topic_id

    @property
    def pack(self) -> TopicPack:
        return get_pack(self.topic_id)

    def select_topic(self, topic_id: str) -> TopicPack:
        """Raises :class:`~app.exceptions.UnknownTopicError` for an unknown id."""
        pack = get_pack(topic_id)
        with self._lock:
            self._config = self._with_topic(self._config, pack.id)
            self._explicit_topic_id = pack.id
        return pack

    @staticmethod
    def _with_topic(config: AppConfig, topic_id: str) -> AppConfig:
        grading = config.grading.model_copy(update={"topic_id": topic_id})
        return config.model_copy(update={"grading": grading})
