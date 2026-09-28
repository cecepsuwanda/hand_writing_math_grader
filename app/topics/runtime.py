"""Active topic pack context (ContextVar) for deep call stacks."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from app.interfaces.topic_pack import TopicPack

_active_pack: ContextVar[TopicPack | None] = ContextVar("active_topic_pack", default=None)


def get_active_pack() -> TopicPack | None:
    return _active_pack.get()


def set_active_pack(pack: TopicPack | None) -> Token[TopicPack | None]:
    return _active_pack.set(pack)


def reset_active_pack(token: Token[TopicPack | None]) -> None:
    _active_pack.reset(token)


@contextmanager
def using_pack(pack: TopicPack) -> Iterator[TopicPack]:
    token = set_active_pack(pack)
    try:
        yield pack
    finally:
        reset_active_pack(token)
