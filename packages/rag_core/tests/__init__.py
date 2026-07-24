"""Hermetic test suite for ``rag_core``.

Every test in this package is **hermetic**: it uses the deterministic
:class:`rag_core.embeddings.HashEmbedder` and an in-process Qdrant ``:memory:``
store, and never touches the network (no Ollama, no Qdrant server, no Docker).
Shared fixtures live in ``conftest.py``.
"""
