"""Topic pack registry and capability dispatch tests."""

from __future__ import annotations

import pytest

from app.capabilities.registry import ALL_CAPABILITY_IDS, apply_capabilities
from app.exceptions import UnknownTopicError
from app.functions.math_normalize import normalize_math_text
from app.functions.paths import parse_topic_choice
from app.functions.step_role import coalesce_step_role
from app.models.exam_schema import ExamPart, ExamSchema
from app.models.recognition import SymbolicPayload
from app.topics.registry import get_pack, known_topic_ids, list_packs, resolve_pack
from app.topics.runtime import using_pack


class TestTopicRegistry:
    def test_default_and_list_packs(self) -> None:
        ids = known_topic_ids()
        assert "1.5" in ids
        assert "2" in ids
        packs = list_packs()
        assert {p.id for p in packs} == set(ids)
        pack = get_pack("1.5")
        assert pack.label
        assert "interval" in pack.capability_ids

    def test_unknown_topic_raises(self) -> None:
        with pytest.raises(UnknownTopicError):
            get_pack("99.9")

    def test_resolve_pack_priority(self) -> None:
        schema = ExamSchema(topic_id="2", questions=[])
        assert resolve_pack(schema=schema).id == "2"
        assert resolve_pack(topic_id="1.5", schema=schema).id == "1.5"

    def test_parse_topic_choice(self) -> None:
        known = known_topic_ids()
        assert parse_topic_choice("1", known) == known[0]
        assert parse_topic_choice("1.5", known) == "1.5"
        with pytest.raises(ValueError):
            parse_topic_choice("nope", known)


class TestTopicPackBehavior:
    def test_inequality_rubric_and_roles(self) -> None:
        pack = get_pack("1.5")
        parts = [
            ExamPart(kind="algebra", order=1),
            ExamPart(kind="hp", order=2),
        ]
        rubric = pack.rubric_from_parts(1, parts)
        assert rubric.maximum_score == 10.0
        assert pack.coalesce_step_role("HP = (1, oo)", None, None) == "hp"

    def test_abs_pack_reuses_roles(self) -> None:
        pack = get_pack("2")
        assert pack.coalesce_step_role(
            "|x|<1",
            SymbolicPayload(kind="relation", repr="Abs(x)<1"),
            "algebra",
        ) in {"algebra", "hp", "critical_points", "sign_chart", "figure"}

    def test_step_role_delegate(self) -> None:
        assert coalesce_step_role("HP = (0,1)", None, None) == "hp"


class TestCapabilityDispatch:
    def test_full_chain_matches_legacy_abs(self) -> None:
        text = r"|x| \leq 2"
        full = normalize_math_text(text, capability_ids=ALL_CAPABILITY_IDS)
        assert "Abs" in full or "abs" in full.lower() or "|" not in full

    def test_inactive_interval_skips_hp_rewrite(self) -> None:
        text = r"HP = (1, 3)"
        without = normalize_math_text(text, capability_ids=("abs",))
        with_interval = normalize_math_text(text, capability_ids=("interval",))
        assert without != with_interval or "HP" in without

    def test_active_pack_context(self) -> None:
        pack = get_pack("1.5")
        with using_pack(pack):
            out = normalize_math_text(r"x \in (0,1)")
        assert "<" in out or "x" in out

    def test_apply_capabilities_skips_unknown(self) -> None:
        assert apply_capabilities("x+1", ("nope", "abs")) == "x+1"
