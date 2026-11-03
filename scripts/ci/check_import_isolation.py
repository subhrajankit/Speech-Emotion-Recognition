#!/usr/bin/env python3
"""
CI Import Isolation Checker.
Validates the core architectural invariant:
ai/ and backend.app.services.speech_service must NEVER import LLM, RAG, or TTS modules.
Perception (ASR, SER, VAD, language routing) remains strictly decoupled from generation and retrieval.
"""

import ast
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


def get_all_python_imports(file_path: Path):
    """Parses Python file AST and returns all imported modules and symbols."""
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(file_path))
    imported_modules = []
    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imported_modules.append(mod)
            for alias in node.names:
                imported_names.append((mod, alias.name))
    return imported_modules, imported_names


def check_forbidden_imports(file_path: Path, forbidden_terms: list[str]) -> list[str]:
    """Returns a list of violation messages if any forbidden terms are imported."""
    violations = []
    modules, names = get_all_python_imports(file_path)

    for mod in modules:
        for term in forbidden_terms:
            parts = mod.split(".")
            if term in parts or term == mod:
                violations.append(f"{file_path}: forbidden module import '{mod}'")

    for mod, name in names:
        for term in forbidden_terms:
            parts = mod.split(".")
            if term in parts or term == name or term == mod:
                violations.append(f"{file_path}: forbidden symbol import '{name}' from '{mod}'")

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    ai_dir = repo_root / "ai"
    speech_service_path = repo_root / "backend" / "app" / "services" / "speech_service.py"

    forbidden_terms = [
        "llm_service",
        "backend.app.services.llm_service",
        "rag",
        "rag_service",
        "backend.app.services.rag_service",
        "vectorstore",
        "retriever",
        "intent_router",
        "tts",
        "tts_service",
        "backend.app.services.tts_service",
        "indic_parler",
        "parler_tts",
    ]

    all_violations = []

    print("[CI Isolation Check] Checking ai/ directory...")
    for py_file in ai_dir.rglob("*.py"):
        v = check_forbidden_imports(py_file, forbidden_terms)
        all_violations.extend(v)

    print(f"[CI Isolation Check] Checking {speech_service_path.relative_to(repo_root)}...")
    if speech_service_path.is_file():
        v = check_forbidden_imports(speech_service_path, forbidden_terms)
        all_violations.extend(v)
    else:
        all_violations.append(f"Missing required file: {speech_service_path}")

    if all_violations:
        print("\n❌ Architectural Isolation Violations Detected:")
        for violation in all_violations:
            print(f"  - {violation}")
        return 1

    print("\n✅ Architectural Isolation Verified: ai/ and speech_service are strictly isolated from LLM, RAG, and TTS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
