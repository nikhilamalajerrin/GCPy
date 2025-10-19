# Shim so `from plancosts.tests.testutils import ...` works even when
# Python resolves `plancosts` to the *inner* package.

try:
    # Prefer re-export from the outer package if available
    from plancosts.tests.testutils import *  # type: ignore  # noqa: F401,F403
except Exception:
    # Fallback to repo-level tests/utils/testutil.py
    import importlib.util
    import sys
    from pathlib import Path

    here = Path(__file__).resolve()
    repo_root = here.parents[3]  # .../plancosts/plancosts/tests -> up 3 = repo root
    util_path = repo_root / "tests" / "utils" / "testutil.py"

    spec = importlib.util.spec_from_file_location("testutil", str(util_path))
    if not spec or not spec.loader:
        raise
    mod = importlib.util.module_from_spec(spec)
    sys.modules["testutil"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]

    for k in dir(mod):
        if not k.startswith("_"):
            globals()[k] = getattr(mod, k)
