"""Structural guards the spec makes CI failures (Part 18.4): the request path never
reaches the law compiler, and no LLM is anywhere in the product (P8)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAWC_FREE = ROOT / "lmpc/server"          # api + svc + obs: nothing here may compile law
LLM_HINTS = ("openai", "anthropic", "transformers", "langchain", "llm")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_request_path_never_imports_the_law_compiler():
    """The law compiler runs offline, on cron, in its own container. A route that
    compiles law per request is a service that stalls on the government's website.
    rulepack.py is start-up glue: it reads the compiled JSON and nothing else."""
    bad = [str(p.relative_to(ROOT)) for p in sorted(LAWC_FREE.rglob("*.py"))
           if p.name != "rulepack.py"
           and any(n.startswith("lmpc.lawc") for n in _imports(p))]
    assert not bad, f"request path imports lmpc.lawc: {bad}"


def test_rulepack_glue_touches_compiled_json_only():
    """The exception stays narrow: only digest/verify/load, never parse or fetch."""
    src = (LAWC_FREE / "rulepack.py").read_text(encoding="utf-8")
    for banned in ("parse", "fetch", "subprocess", "urllib", "requests"):
        assert banned not in src, f"rulepack.py references {banned}"


def test_no_llm_package_is_imported_anywhere():
    bad = []
    for p in sorted((ROOT / "lmpc").rglob("*.py")):
        joined = " ".join(_imports(p)).lower()
        if any(h in joined for h in LLM_HINTS):
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, f"LLM-shaped imports in the product (P8): {bad}"


def test_no_file_grows_unbounded():
    """Conventions: <= 300 lines per file; routers and API modules <= 200."""
    bad = []
    for p in sorted((ROOT / "lmpc").rglob("*.py")):
        n = len(p.read_text(encoding="utf-8").splitlines())
        cap = 300 if "server/api" not in str(p) else 200
        if n > cap:
            bad.append(f"{p.relative_to(ROOT)}: {n} > {cap}")
    assert not bad, "files over the line budget: " + ", ".join(bad)