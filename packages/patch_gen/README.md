# patch_gen — CareerForge AI Phase 9

Candidate patch generation. From a static finding (`path:line` + category),
produces 2-3 independent candidates plus a NO_SUBMISSION critic:

- **Template mode (always works, offline/VPN):** deterministic transforms
  (narrow bare `except:`, replace mutable default with `None`, disable
  `shell=True`, ...). The diff is computed from real source via `difflib` —
  never hallucinated.
- **LLM mode (when a local Ollama is reachable):** enriches the root-cause
  narrative with the local model (`qwen2.5:7b` by default). The *diff* stays
  deterministic even in LLM mode.

Graceful degradation: if Ollama is unreachable (no server, VPN, cold-load
timeout) it silently falls back to template mode. `patch_gen.probe()` reports
availability for bootup / health checks.

```python
from patch_gen import PatchGenerator, LocalLLM
llm = LocalLLM()                      # optional
gen = PatchGenerator(llm)             # or PatchGenerator() for template-only
cset = await gen.generate_for_finding(
    repo_root, finding_id="f1", summary="Bare `except:` ...",
    category="SECURITY_SMELL", path="pkg/bad.py", line=6, snippet="except:")
```

Tests are hermetic (LLM disabled), so they pass with no network.
