#!/usr/bin/env python3
"""
Runs the full OS42 Orchestrator test suite in one command: every
standalone test_phase_*.py / test_*.py script (auto-discovered, each
already designed to run as its own fresh process with its own
module-level singletons - see any of them for why) plus the pytest suite
under tests/. Prints one pass/fail line per file and exits non-zero if
anything failed.

This is exactly what CI (.github/workflows/tests.yml) runs, and what you
should run locally before pushing.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent

# Auto-discovered so a new test_phase_*.py file is picked up automatically -
# nothing to remember to register here.
STANDALONE_TESTS = sorted(
    p for p in REPO_ROOT.glob("test_*.py") if p.name != Path(__file__).name
)


def run(cmd, label: str) -> bool:
    print("\n" + "#" * 70)
    print(f"# {label}")
    print("#" * 70)
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode == 0


def main() -> bool:
    results: dict[str, bool] = {}

    for test_file in STANDALONE_TESTS:
        results[test_file.name] = run([sys.executable, str(test_file)], test_file.name)

    results["pytest tests/"] = run([sys.executable, "-m", "pytest", "tests/", "-q"], "pytest tests/")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")

    all_passed = all(results.values())
    print("\n" + ("[OK] ALL TESTS PASSED" if all_passed else "[FAIL] SOME TESTS FAILED"))
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
