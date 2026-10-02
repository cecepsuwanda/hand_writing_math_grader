"""Interactive main menu: session state + dispatch to :class:`MenuActions`."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from app.config import AppConfig, require_vision_model
from app.exceptions import InvalidMenuSelectionError, MathGraderError
from app.functions.menu_choices import MenuChoice, parse_main_menu_choice
from app.functions.run_layout import RunLayout, layout_for_pdf
from app.functions.standards_layout import topic_standard_dir
from app.interfaces.menu_actions import MenuActions
from app.models.question_crops import LabelMode
from app.topics.registry import get_pack
from app.views.error_view import print_error
from app.views.exit_view import mark_interactive_session_done
from app.views.prompt_view import InputFn
from app.views.selection_view import print_main_menu, prompt_main_menu_choice

logger = logging.getLogger(__name__)


class MenuSession(BaseModel):
    """State carried between menu entries within one ``menu`` run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    topic_id: str
    # None until the user picks a topic, so grading follows exam_schema.topic_id
    # exactly like CLI ``process``.
    explicit_topic_id: str | None = None
    layout: RunLayout | None = None
    last_code: int = 0


def exit_code_for(exc: BaseException) -> int:
    """1 for domain errors the user can fix, 2 for anything unexpected."""
    return 1 if isinstance(exc, MathGraderError) else 2


class MenuController:
    def __init__(
        self,
        actions: MenuActions,
        config: AppConfig,
        *,
        topic_id: str | None = None,
        input_fn: InputFn | None = None,
    ) -> None:
        self._actions = actions
        self._config = config
        self._requested_topic_id = topic_id or None
        self._input_fn = input_fn
        self._handlers: dict[MenuChoice, Callable[[MenuSession], None]] = {
            MenuChoice.SELECT_TOPIC: self._select_topic,
            MenuChoice.INGEST: self._ingest,
            MenuChoice.PROPOSE_CROPS: self._propose_crops,
            MenuChoice.RECROP: self._recrop,
            MenuChoice.LABEL_QUESTIONS: self._label(LabelMode.LABEL),
            MenuChoice.RELABEL_QUESTIONS: self._label(LabelMode.RELABEL),
            MenuChoice.FINISH: self._finish,
            MenuChoice.FINISH_QUESTIONS: self._finish_questions,
        }

    @property
    def config(self) -> AppConfig:
        return self._config

    def start_session(self) -> MenuSession:
        """Validate the starting topic (raises :class:`UnknownTopicError`)."""
        pack = get_pack(self._requested_topic_id or self._config.grading.topic_id)
        # Steps that read config (label, finish) must use the same topik_<bab> folder.
        self._set_config_topic(pack.id)
        return MenuSession(
            topic_id=pack.id,
            explicit_topic_id=pack.id if self._requested_topic_id else None,
        )

    def run(self) -> int:
        session = self.start_session()
        while True:
            pack = get_pack(session.topic_id)
            print_main_menu(
                active_topic_label=pack.label,
                active_topic_id=pack.id,
                standard_dir=topic_standard_dir(
                    self._config.grading.standards_root, pack.id
                ),
            )
            raw = prompt_main_menu_choice(input_fn=self._input_fn)
            if raw is None:
                break
            try:
                choice = parse_main_menu_choice(raw)
            except ValueError as exc:
                print_error(InvalidMenuSelectionError(str(exc)))
                continue
            if choice is MenuChoice.EXIT:
                break
            session.last_code = self.dispatch(session, choice)
        mark_interactive_session_done()
        return session.last_code

    def dispatch(self, session: MenuSession, choice: MenuChoice) -> int:
        """Run one menu entry; errors are shown and mapped to an exit code."""
        handler = self._handlers.get(choice)
        try:
            if handler is None:
                raise InvalidMenuSelectionError(f"unhandled choice: {choice}")
            handler(session)
        except Exception as exc:  # noqa: BLE001 — menu keeps running after any failure
            code = exit_code_for(exc)
            if code == 2:
                logger.exception("Unexpected error in menu entry %s", choice)
            print_error(exc)
            return code
        return 0

    def _ensure_layout(self, session: MenuSession) -> RunLayout:
        if session.layout is None:
            session.layout = self._actions.pick_run(self._config)
        return session.layout

    def _select_topic(self, session: MenuSession) -> None:
        chosen = self._actions.select_topic(session.topic_id)
        if chosen is None:
            return
        session.topic_id = chosen
        session.explicit_topic_id = chosen
        self._set_config_topic(chosen)

    def _set_config_topic(self, topic_id: str) -> None:
        grading = self._config.grading.model_copy(update={"topic_id": topic_id})
        self._config = self._config.model_copy(update={"grading": grading})

    def _ingest(self, session: MenuSession) -> None:
        self._actions.ingest(self._config, session.topic_id)

    def _propose_crops(self, session: MenuSession) -> None:
        pdf_path = self._actions.select_pdf(self._config)
        session.layout = layout_for_pdf(self._config.output.root_dir, pdf_path)
        self._actions.propose_crops(self._config, session.layout, pdf_path)

    def _recrop(self, session: MenuSession) -> None:
        self._actions.recrop(self._config, self._ensure_layout(session))

    def _label(self, mode: LabelMode) -> Callable[[MenuSession], None]:
        def handler(session: MenuSession) -> None:
            self._actions.label(self._config, self._ensure_layout(session), mode)

        return handler

    def _finish(self, session: MenuSession) -> None:
        require_vision_model(self._config)
        self._actions.finish(
            self._config, self._ensure_layout(session), session.explicit_topic_id
        )

    def _finish_questions(self, session: MenuSession) -> None:
        self._actions.finish_questions(
            self._config, self._ensure_layout(session), session.explicit_topic_id
        )
