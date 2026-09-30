"""Pure parsing for interactive menu answers (main menu, topic, yes/no, continue)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, NamedTuple


class MenuChoice(StrEnum):
    SELECT_TOPIC = "select_topic"
    INGEST = "ingest"
    PROPOSE_CROPS = "propose_crops"
    RECROP = "recrop"
    LABEL_QUESTIONS = "label_questions"
    RELABEL_QUESTIONS = "relabel_questions"
    FINISH = "finish"
    EXIT = "exit"


class MenuEntry(NamedTuple):
    choice: MenuChoice
    label: str
    aliases: frozenset[str]


MAIN_MENU: tuple[MenuEntry, ...] = (
    MenuEntry(
        MenuChoice.SELECT_TOPIC,
        "Pilih topik grader",
        frozenset({"topic", "topik", "t", "select_topic", "select-topic"}),
    ),
    MenuEntry(
        MenuChoice.INGEST,
        "Ingest kunci jawaban (.tex)",
        frozenset({"ingest", "kunci", "i"}),
    ),
    MenuEntry(
        MenuChoice.PROPOSE_CROPS,
        "Pilih PDF → render halaman → crop ink (konfirmasi)",
        frozenset({"propose-crops", "propose_crops", "propose", "crop", "c", "pdf"}),
    ),
    MenuEntry(
        MenuChoice.RECROP,
        "Crop ulang dari page_*_regions.json",
        frozenset({"recrop", "re-crop", "r"}),
    ),
    MenuEntry(
        MenuChoice.LABEL_QUESTIONS,
        "Kenali nomor soal → question_crops/question_*.json",
        frozenset({"label", "nomor", "label-questions", "label_questions", "l"}),
    ),
    MenuEntry(
        MenuChoice.RELABEL_QUESTIONS,
        "Muat ulang nomor soal dari question_*.json",
        frozenset({"relabel", "relabel-questions", "relabel_questions"}),
    ),
    MenuEntry(
        MenuChoice.FINISH,
        "Lanjutkan grading (recognize → report) dari crops",
        frozenset({"finish", "lanjut", "grade", "proses", "process", "p"}),
    ),
    MenuEntry(
        MenuChoice.EXIT,
        "Keluar",
        frozenset({"exit", "keluar", "q"}),
    ),
)

MAIN_MENU_PROMPT = f"Pilihan [1-{len(MAIN_MENU)}]: "

ContinueOrExit = Literal["continue", "exit"]

_YES = frozenset({"", "y", "yes"})
_NO = frozenset({"n", "no"})
_CONTINUE = frozenset({"1", "lanjut", "continue", "c", "y", "ya"})
_EXIT = frozenset({"2", "keluar", "exit", "q", "n", "tidak"})


def parse_main_menu_choice(raw: str) -> MenuChoice:
    """Map a 1-based index or alias to a :class:`MenuChoice`.

    Raises:
        ValueError: if the choice is empty or unknown.
    """
    choice = raw.strip().lower()
    if not choice:
        raise ValueError("empty selection")
    for index, entry in enumerate(MAIN_MENU, start=1):
        if choice == str(index) or choice in entry.aliases:
            return entry.choice
    raise ValueError(f"unknown menu choice: {raw.strip()}")


def parse_topic_choice(raw: str, known_ids: list[str]) -> str:
    """Map menu choice (1-based index or pack id) to a topic id.

    Raises:
        ValueError: if empty or unknown.
    """
    choice = raw.strip()
    if not choice:
        raise ValueError("empty selection")
    if choice in known_ids:
        return choice
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(known_ids):
            return known_ids[index - 1]
    raise ValueError(f"unknown topic: {choice}")


def parse_yes_no(raw: str) -> bool:
    """Empty / y / yes → True; n / no → False.

    Raises:
        ValueError: for any other answer.
    """
    answer = raw.strip().lower()
    if answer in _YES:
        return True
    if answer in _NO:
        return False
    raise ValueError(f"expected y or n, got {raw.strip()!r}")


def parse_continue_or_exit(raw: str) -> ContinueOrExit:
    """Map the post-process prompt answer to ``continue`` / ``exit``.

    Raises:
        ValueError: for any other answer.
    """
    answer = raw.strip().lower()
    if answer in _CONTINUE:
        return "continue"
    if answer in _EXIT:
        return "exit"
    raise ValueError(f"unknown choice: {raw.strip()}")
