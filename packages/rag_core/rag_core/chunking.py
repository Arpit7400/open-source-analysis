"""Content-aware chunkers for code, Markdown, and plain text.

The RAG contract (handbook §5.3) is explicit: **never fixed token windows for
code**. Instead we chunk by *semantic unit*:

* Python source → one :class:`~rag_core.models.Chunk` per top-level function,
  per class, per method (dotted ``symbol``), plus a module-docstring chunk.
* Markdown/reStructuredText → one chunk per heading section, preserving the
  heading path in ``metadata``.
* Everything else → sliding sentence/paragraph windows with overlap.

Design constraints honoured throughout:

* **Deterministic.** Parsing uses the stdlib :mod:`ast`; ordering is stable
  (source order for code/markdown, positional for text). Given the same inputs
  a chunker always emits the same chunks in the same order with the same ids.
* **Robust.** A Python file that fails to parse degrades to a single whole-file
  text chunk (logged), never an exception.
* **Provenance-complete.** Line ranges (via ``ast`` ``end_lineno``), symbols,
  module-level imports, language and ``source_type`` (``CODE`` vs ``TEST``) are
  captured so downstream citations are exact.
* **Cross-platform.** File classification uses :mod:`pathlib` semantics and is
  agnostic to path separators.

The public entry point is :func:`chunk_file`, which dispatches to the right
chunker by file extension and stamps stable ids via :meth:`Chunk.make_id`.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Iterable
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from rag_core.models import Chunk

logger = logging.getLogger(__name__)

# Extensions treated as Markdown-style structured docs.
_MARKDOWN_EXTS: frozenset[str] = frozenset({".md", ".markdown", ".mdx", ".rst"})
# Extensions parsed with the Python AST chunker.
_PYTHON_EXTS: frozenset[str] = frozenset({".py", ".pyi"})

# Heading detection: ATX Markdown (``#``..``######``) at line start.
_MD_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
# Sentence boundary: end punctuation followed by whitespace.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _normalise_path(path: str) -> str:
    """Return a forward-slash, OS-agnostic view of ``path`` for classification."""
    if "\\" in path and "/" not in path:
        return PureWindowsPath(path).as_posix()
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _extension(path: str) -> str:
    """Lower-cased file suffix (``".py"``) using OS-agnostic parsing."""
    return PurePosixPath(_normalise_path(path)).suffix.lower()


def _classify_code_source(path: str) -> str:
    """Return ``"TEST"`` for test files/dirs, else ``"CODE"`` (handbook §5.3)."""
    posix = _normalise_path(path)
    name = PurePosixPath(posix).name.lower()
    parts = {part.lower() for part in PurePosixPath(posix).parts}
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.pyi"):
        return "TEST"
    if "tests" in parts or "test" in parts:
        return "TEST"
    return "CODE"


class PythonAstChunker:
    """Chunk Python source into function / class / method / docstring units."""

    language = "python"

    def chunk(
        self,
        *,
        path: str,
        text: str,
        domain: str,
        source_id: str | None,
        commit: str | None,
    ) -> list[Chunk]:
        """Return semantic chunks for ``text``.

        On a :class:`SyntaxError` (or any parse failure) this logs a warning and
        falls back to a single whole-file ``TEST``/``CODE`` text chunk so a
        malformed file is still indexed rather than dropped.
        """
        source_type = _classify_code_source(path)
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError) as exc:
            logger.warning(
                "AST parse failed for %s (%s); emitting whole-file fallback chunk.",
                path,
                exc,
            )
            return self._fallback_chunk(
                path=path,
                text=text,
                domain=domain,
                source_id=source_id,
                commit=commit,
                source_type=source_type,
            )

        imports = self._module_imports(tree)
        lines = text.splitlines()
        chunks: list[Chunk] = []

        # 1) Module docstring chunk (if present), so file-level intent is indexed.
        module_doc = ast.get_docstring(tree, clean=False)
        if module_doc and module_doc.strip():
            doc_node = tree.body[0]  # docstring is always the first statement
            start = getattr(doc_node, "lineno", 1)
            end = getattr(doc_node, "end_lineno", start)
            chunks.append(
                self._build(
                    path=path,
                    text=module_doc,
                    domain=domain,
                    source_id=source_id,
                    commit=commit,
                    source_type=source_type,
                    symbol="<module>",
                    start_line=start,
                    end_line=end,
                    imports=imports,
                )
            )

        # 2) Top-level functions & classes (and each method inside a class).
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.append(
                    self._symbol_chunk(
                        node=node,
                        symbol=node.name,
                        path=path,
                        lines=lines,
                        domain=domain,
                        source_id=source_id,
                        commit=commit,
                        source_type=source_type,
                        imports=imports,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                chunks.append(
                    self._symbol_chunk(
                        node=node,
                        symbol=node.name,
                        path=path,
                        lines=lines,
                        domain=domain,
                        source_id=source_id,
                        commit=commit,
                        source_type=source_type,
                        imports=imports,
                    )
                )
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        chunks.append(
                            self._symbol_chunk(
                                node=member,
                                symbol=f"{node.name}.{member.name}",
                                path=path,
                                lines=lines,
                                domain=domain,
                                source_id=source_id,
                                commit=commit,
                                source_type=source_type,
                                imports=imports,
                            )
                        )

        # If a file has neither docstring nor any defs (e.g. pure script), index
        # the whole file so nothing is silently lost.
        if not chunks:
            return self._fallback_chunk(
                path=path,
                text=text,
                domain=domain,
                source_id=source_id,
                commit=commit,
                source_type=source_type,
            )
        return chunks

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _module_imports(tree: ast.Module) -> list[str]:
        """Collect module-level imported names in deterministic source order."""
        names: list[str] = []
        seen: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in seen:
                        seen.add(alias.name)
                        names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                prefix = "." * (node.level or 0)
                base = f"{prefix}{module}" if module else prefix
                for alias in node.names:
                    full = f"{base}.{alias.name}" if base else alias.name
                    if full not in seen:
                        seen.add(full)
                        names.append(full)
        return names

    def _symbol_chunk(
        self,
        *,
        node: ast.AST,
        symbol: str,
        path: str,
        lines: list[str],
        domain: str,
        source_id: str | None,
        commit: str | None,
        source_type: str,
        imports: list[str],
    ) -> Chunk:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start) or start
        # Include the decorator lines so the captured source is faithful.
        decorators = getattr(node, "decorator_list", []) or []
        if decorators:
            deco_start = min(getattr(d, "lineno", start) for d in decorators)
            start = min(start, deco_start)
        snippet = "\n".join(lines[start - 1 : end])
        return self._build(
            path=path,
            text=snippet,
            domain=domain,
            source_id=source_id,
            commit=commit,
            source_type=source_type,
            symbol=symbol,
            start_line=start,
            end_line=end,
            imports=imports,
        )

    def _fallback_chunk(
        self,
        *,
        path: str,
        text: str,
        domain: str,
        source_id: str | None,
        commit: str | None,
        source_type: str,
    ) -> list[Chunk]:
        line_count = max(1, len(text.splitlines()))
        return [
            self._build(
                path=path,
                text=text,
                domain=domain,
                source_id=source_id,
                commit=commit,
                source_type=source_type,
                symbol=None,
                start_line=1,
                end_line=line_count,
                imports=[],
            )
        ]

    def _build(
        self,
        *,
        path: str,
        text: str,
        domain: str,
        source_id: str | None,
        commit: str | None,
        source_type: str,
        symbol: str | None,
        start_line: int,
        end_line: int,
        imports: list[str],
    ) -> Chunk:
        return Chunk(
            id=Chunk.make_id(domain, source_id, path, start_line, end_line),
            domain=domain,
            text=text,
            source_id=source_id,
            source_type=source_type,
            path=path,
            symbol=symbol,
            start_line=start_line,
            end_line=end_line,
            language=self.language,
            commit=commit,
            imports=list(imports),
        )


class MarkdownSectionChunker:
    """Split Markdown/reST into one chunk per heading section.

    The heading path (breadcrumbs from all ancestor headings, e.g.
    ``"Guide > Install > macOS"``) is preserved in ``metadata["heading_path"]``
    and the leaf heading in ``metadata["heading"]`` so citations can name the
    section. Content before the first heading becomes a leading "preamble"
    section so nothing is dropped.
    """

    language = "markdown"

    def chunk(
        self,
        *,
        path: str,
        text: str,
        domain: str,
        source_id: str | None,
        commit: str | None,
    ) -> list[Chunk]:
        lines = text.splitlines()
        sections = self._split_sections(lines)
        chunks: list[Chunk] = []
        for section in sections:
            body = section["text"]
            if not body.strip():
                continue
            chunks.append(
                Chunk(
                    id=Chunk.make_id(
                        domain, source_id, path, section["start"], section["end"]
                    ),
                    domain=domain,
                    text=body,
                    source_id=source_id,
                    source_type="DOC",
                    path=path,
                    symbol=section["heading"] or None,
                    start_line=section["start"],
                    end_line=section["end"],
                    language=self.language,
                    commit=commit,
                    metadata={
                        "heading": section["heading"],
                        "heading_path": section["heading_path"],
                    },
                )
            )
        if not chunks:
            # Empty/whitespace-only doc: still index a single placeholder chunk.
            line_count = max(1, len(lines))
            chunks.append(
                Chunk(
                    id=Chunk.make_id(domain, source_id, path, 1, line_count),
                    domain=domain,
                    text=text,
                    source_id=source_id,
                    source_type="DOC",
                    path=path,
                    start_line=1,
                    end_line=line_count,
                    language=self.language,
                    commit=commit,
                )
            )
        return chunks

    @staticmethod
    def _split_sections(lines: list[str]) -> list[dict[str, Any]]:
        """Return ordered section dicts with heading, path, text, line range."""
        sections: list[dict[str, Any]] = []
        stack: list[tuple[int, str]] = []  # (level, title) breadcrumb stack

        def heading_path(title: str) -> str:
            crumbs = [t for _, t in stack] + [title]
            return " > ".join(crumbs)

        current_start = 1
        current_heading = ""
        current_path = ""
        buffer: list[str] = []

        def flush(end_line: int) -> None:
            if buffer or current_heading:
                sections.append(
                    {
                        "heading": current_heading,
                        "heading_path": current_path,
                        "text": "\n".join(buffer).strip("\n"),
                        "start": current_start,
                        "end": max(end_line, current_start),
                    }
                )

        for idx, line in enumerate(lines, start=1):
            match = _MD_HEADING_RE.match(line)
            if match:
                # Close the previous section at the line before this heading.
                flush(idx - 1)
                level = len(match.group("hashes"))
                title = match.group("title").strip()
                # Maintain breadcrumb stack: pop deeper-or-equal levels.
                while stack and stack[-1][0] >= level:
                    stack.pop()
                current_path = heading_path(title)
                stack.append((level, title))
                current_heading = title
                current_start = idx
                buffer = [line]
            else:
                buffer.append(line)

        flush(len(lines))
        return sections


class TextChunker:
    """Sliding sentence/paragraph windows with overlap for plain text.

    Sentences are grouped into windows of up to ``max_chars`` characters; the
    last ``overlap_chars`` characters of each window are carried into the next so
    context spanning a boundary is not lost. Deterministic given identical
    inputs and settings.
    """

    language = "text"

    def __init__(self, max_chars: int = 1200, overlap_chars: int = 200) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be in [0, max_chars)")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(
        self,
        *,
        path: str,
        text: str,
        domain: str,
        source_id: str | None,
        commit: str | None,
    ) -> list[Chunk]:
        windows = self._windows(text)
        line_offsets = self._line_offsets(text)
        chunks: list[Chunk] = []
        for start_char, end_char, window_text in windows:
            if not window_text.strip():
                continue
            start_line = self._char_to_line(start_char, line_offsets)
            end_line = self._char_to_line(max(start_char, end_char - 1), line_offsets)
            chunks.append(
                Chunk(
                    id=Chunk.make_id(domain, source_id, path, start_line, end_line),
                    domain=domain,
                    text=window_text,
                    source_id=source_id,
                    source_type="DOC",
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    language=self.language,
                    commit=commit,
                )
            )
        if not chunks:
            line_count = max(1, len(text.splitlines()))
            chunks.append(
                Chunk(
                    id=Chunk.make_id(domain, source_id, path, 1, line_count),
                    domain=domain,
                    text=text,
                    source_id=source_id,
                    source_type="DOC",
                    path=path,
                    start_line=1,
                    end_line=line_count,
                    language=self.language,
                    commit=commit,
                )
            )
        return chunks

    def _windows(self, text: str) -> list[tuple[int, int, str]]:
        """Greedy sentence-packed windows with a character overlap tail."""
        sentences = self._sentences(text)
        if not sentences:
            return []
        windows: list[tuple[int, int, str]] = []
        i = 0
        n = len(sentences)
        while i < n:
            win_start = sentences[i][0]
            j = i
            win_end = sentences[i][1]
            while j < n and (sentences[j][1] - win_start) <= self.max_chars:
                win_end = sentences[j][1]
                j += 1
            if j == i:  # a single sentence longer than max_chars
                win_end = sentences[i][1]
                j = i + 1
            windows.append((win_start, win_end, text[win_start:win_end].strip()))
            if j >= n:
                break
            # Advance start so the next window overlaps by ~overlap_chars.
            next_start_char = max(win_start, win_end - self.overlap_chars)
            i = self._sentence_index_at_or_after(sentences, next_start_char, j, i)
        return windows

    @staticmethod
    def _sentence_index_at_or_after(
        sentences: list[tuple[int, int]], char: int, hard_stop: int, prev: int
    ) -> int:
        """Return the first sentence index whose start >= ``char``.

        Falls back to ``hard_stop`` to guarantee forward progress (never returns
        an index <= ``prev``), keeping the window loop terminating.
        """
        for idx in range(prev, hard_stop + 1):
            if idx < len(sentences) and sentences[idx][0] >= char:
                return max(idx, prev + 1)
        return max(hard_stop, prev + 1)

    @staticmethod
    def _sentences(text: str) -> list[tuple[int, int]]:
        """Return ``(start, end)`` char offsets for each sentence span."""
        spans: list[tuple[int, int]] = []
        cursor = 0
        for piece in _SENTENCE_SPLIT_RE.split(text):
            if piece == "":
                continue
            start = text.find(piece, cursor)
            if start < 0:
                start = cursor
            end = start + len(piece)
            spans.append((start, end))
            cursor = end
        return spans

    @staticmethod
    def _line_offsets(text: str) -> list[int]:
        """Character offset at which each 1-indexed line begins."""
        offsets = [0]
        for idx, ch in enumerate(text):
            if ch == "\n":
                offsets.append(idx + 1)
        return offsets

    @staticmethod
    def _char_to_line(char: int, line_offsets: list[int]) -> int:
        """Map a character offset to its 1-indexed line via binary search."""
        lo, hi = 0, len(line_offsets) - 1
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if line_offsets[mid] <= char:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best + 1


def chunk_file(
    path: str,
    text: str,
    domain: str,
    source_id: str | None = None,
    commit: str | None = None,
) -> list[Chunk]:
    """Dispatch ``(path, text)`` to the right chunker by file extension.

    * ``.py`` / ``.pyi`` → :class:`PythonAstChunker`
    * ``.md`` / ``.markdown`` / ``.mdx`` / ``.rst`` → :class:`MarkdownSectionChunker`
    * anything else → :class:`TextChunker`

    Returns a list of fully-populated, id-stamped :class:`Chunk` objects in a
    deterministic order. ``source_id`` and ``commit`` are threaded into every
    chunk for provenance.
    """
    ext = _extension(path)
    chunker: PythonAstChunker | MarkdownSectionChunker | TextChunker
    if ext in _PYTHON_EXTS:
        chunker = PythonAstChunker()
    elif ext in _MARKDOWN_EXTS:
        chunker = MarkdownSectionChunker()
    else:
        chunker = TextChunker()
    return chunker.chunk(
        path=path,
        text=text,
        domain=domain,
        source_id=source_id,
        commit=commit,
    )


def chunk_files(
    files: Iterable[tuple[str, str]],
    domain: str,
    source_id: str | None = None,
    commit: str | None = None,
) -> list[Chunk]:
    """Chunk many ``(path, text)`` pairs, preserving input order deterministically."""
    result: list[Chunk] = []
    for path, text in files:
        result.extend(chunk_file(path, text, domain, source_id, commit))
    return result


__all__ = [
    "MarkdownSectionChunker",
    "PythonAstChunker",
    "TextChunker",
    "chunk_file",
    "chunk_files",
]
