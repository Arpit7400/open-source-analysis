"""AST chunking tests (RAG_CONTRACT.md § *Code-aware indexing*).

Verifies the :class:`~rag_core.chunking.PythonAstChunker` on a known snippet:
correct symbols, line ranges, imports, and CODE-vs-TEST source classification.
Hermetic: pure stdlib ``ast``, no network.
"""

from __future__ import annotations

from rag_core.chunking import chunk_file
from rag_core.domains import REPOSITORY_CODE
from rag_core.models import Chunk

# A small, known Python module: module docstring, an import, a top-level
# function, and a class with a method. Line numbers below are 1-indexed and
# must match the AST-reported ranges exactly.
_SNIPPET = '''\
"""Module docstring for the sample."""

import os


def greet(name):
    return f"hello {name}"


class Widget:
    """A widget."""

    def render(self):
        return os.getcwd()
'''


def _by_symbol(chunks: list[Chunk]) -> dict[str | None, Chunk]:
    return {c.symbol: c for c in chunks}


def test_ast_chunker_extracts_expected_symbols() -> None:
    chunks = chunk_file(
        "sample.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo", commit="deadbeef"
    )
    symbols = {c.symbol for c in chunks}
    # Module docstring chunk uses the "<module>" symbol; function, class, method.
    assert symbols == {"<module>", "greet", "Widget", "Widget.render"}


def test_ast_chunker_line_ranges_and_language() -> None:
    chunks = _by_symbol(
        chunk_file("sample.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo")
    )

    module_doc = chunks["<module>"]
    assert module_doc.start_line == 1
    assert module_doc.end_line == 1

    greet = chunks["greet"]
    assert greet.start_line == 6
    assert greet.end_line == 7
    assert 'f"hello {name}"' in greet.text
    assert greet.language == "python"

    widget = chunks["Widget"]
    assert widget.start_line == 10
    # The class spans through its last method line (line 14, the last content
    # line of the snippet).
    assert widget.end_line == 14

    render = chunks["Widget.render"]
    assert render.start_line == 13
    assert render.end_line == 14
    assert "os.getcwd()" in render.text


def test_ast_chunker_records_imports_and_provenance() -> None:
    chunks = chunk_file(
        "sample.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo", commit="c0ffee"
    )
    greet = _by_symbol(chunks)["greet"]
    assert "os" in greet.imports
    assert greet.source_id == "acme/repo"
    assert greet.commit == "c0ffee"
    assert greet.domain == REPOSITORY_CODE


def test_source_type_code_vs_test_detection() -> None:
    impl = chunk_file("pkg/module.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo")
    assert all(c.source_type == "CODE" for c in impl)

    # A ``test_``-prefixed file, and a file under a ``tests/`` directory, are TEST.
    test_by_name = chunk_file(
        "test_module.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo"
    )
    assert all(c.source_type == "TEST" for c in test_by_name)

    test_by_dir = chunk_file(
        "tests/module.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo"
    )
    assert all(c.source_type == "TEST" for c in test_by_dir)


def test_chunk_ids_are_stable_and_deterministic() -> None:
    first = chunk_file("sample.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo")
    second = chunk_file("sample.py", _SNIPPET, REPOSITORY_CODE, source_id="acme/repo")
    assert [c.id for c in first] == [c.id for c in second]
    # And the id matches the contract derivation for the greet symbol.
    greet = _by_symbol(first)["greet"]
    assert greet.id == Chunk.make_id(
        REPOSITORY_CODE, "acme/repo", "sample.py", greet.start_line, greet.end_line
    )


def test_malformed_python_degrades_to_whole_file_chunk() -> None:
    broken = "def oops(:\n    pass\n"
    chunks = chunk_file("broken.py", broken, REPOSITORY_CODE, source_id="acme/repo")
    assert len(chunks) == 1
    assert chunks[0].text == broken
    assert chunks[0].start_line == 1
