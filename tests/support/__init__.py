"""Shared test support, split MVC-style.

- ``builders``: Model — factories for domain objects and on-disk fixtures.
- ``fakes``: doubles for ports (Ollama client, proposer, judge, process controller).
- ``harness``: Controller — wires fakes + temp workspace and drives the code under test.
- ``asserts``: View — reusable assertions on results and CLI output.

Import from the submodule explicitly, e.g. ``from tests.support.builders import make_question``.
"""
