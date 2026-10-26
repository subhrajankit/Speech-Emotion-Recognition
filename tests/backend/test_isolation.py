"""
Architectural isolation tests for VoiceSense AI.
Uses AST analysis to guarantee that:
1. Nothing under ai/ imports backend.app.services.llm_service or llm_service.
2. backend.app.services.speech_service does not import llm_service.
"""

import ast
from pathlib import Path
import pytest


def get_all_python_imports(file_path: Path):
    """Parses a Python file and returns all imported module names and imported symbols."""
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


def test_ai_package_does_not_import_llm_service():
    """
    Scans every file under ai/ directory and asserts that zero files import
    llm_service or backend.app.services.llm_service.
    """
    ai_dir = Path("ai")
    assert ai_dir.is_dir(), "ai/ directory must exist"

    ai_py_files = list(ai_dir.rglob("*.py"))
    assert len(ai_py_files) > 0, "ai/ must contain python source files"

    forbidden_patterns = ["llm_service", "backend.app.services.llm_service"]

    for py_file in ai_py_files:
        modules, names = get_all_python_imports(py_file)

        for mod in modules:
            for forbidden in forbidden_patterns:
                assert forbidden not in mod, (
                    f"Architectural isolation violation: {py_file} imports '{mod}', "
                    f"which violates the ASR/LLM decoupling invariant."
                )

        for mod, name in names:
            for forbidden in forbidden_patterns:
                assert forbidden != name and forbidden != mod, (
                    f"Architectural isolation violation: {py_file} imports '{name}' from '{mod}', "
                    f"which violates the ASR/LLM decoupling invariant."
                )


def test_speech_service_does_not_import_llm_service():
    """
    Asserts that backend/app/services/speech_service.py does not import llm_service.
    Speech perception and language routing must remain 100% decoupled from LLM reasoning.
    """
    speech_service_path = Path("backend/app/services/speech_service.py")
    assert speech_service_path.is_file(), "speech_service.py must exist"

    modules, names = get_all_python_imports(speech_service_path)
    forbidden_patterns = ["llm_service", "backend.app.services.llm_service"]

    for mod in modules:
        for forbidden in forbidden_patterns:
            assert forbidden not in mod, (
                f"Architectural isolation violation: speech_service.py imports '{mod}', "
                f"which violates the ASR/LLM decoupling invariant."
            )

    for mod, name in names:
        for forbidden in forbidden_patterns:
            assert forbidden != name and forbidden != mod, (
                f"Architectural isolation violation: speech_service.py imports '{name}' from '{mod}', "
                f"which violates the ASR/LLM decoupling invariant."
            )


def test_ai_package_does_not_import_rag():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Scans every file under ai/ directory and asserts that ZERO files import
    rag, rag_service, or any RAG components.
    """
    ai_dir = Path("ai")
    assert ai_dir.is_dir(), "ai/ directory must exist"

    ai_py_files = list(ai_dir.rglob("*.py"))
    assert len(ai_py_files) > 0, "ai/ must contain python source files"

    forbidden_patterns = [
        "rag",
        "rag_service",
        "backend.app.services.rag_service",
        "vectorstore",
        "retriever",
        "intent_router",
    ]

    for py_file in ai_py_files:
        modules, names = get_all_python_imports(py_file)

        for mod in modules:
            for forbidden in forbidden_patterns:
                # Match exact module or submodule
                parts = mod.split(".")
                assert forbidden not in parts, (
                    f"Architectural isolation violation: {py_file} imports '{mod}', "
                    f"which violates the ASR/RAG decoupling invariant."
                )

        for mod, name in names:
            for forbidden in forbidden_patterns:
                parts = mod.split(".")
                assert forbidden not in parts and forbidden != name, (
                    f"Architectural isolation violation: {py_file} imports '{name}' from '{mod}', "
                    f"which violates the ASR/RAG decoupling invariant."
                )


def test_speech_service_does_not_import_rag():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Asserts that backend/app/services/speech_service.py does not import RAG.
    ASR, SER, and language routing must NEVER import or depend on RAG.
    """
    speech_service_path = Path("backend/app/services/speech_service.py")
    assert speech_service_path.is_file(), "speech_service.py must exist"

    modules, names = get_all_python_imports(speech_service_path)
    forbidden_patterns = [
        "rag",
        "rag_service",
        "backend.app.services.rag_service",
        "vectorstore",
        "retriever",
        "intent_router",
    ]

    for mod in modules:
        for forbidden in forbidden_patterns:
            parts = mod.split(".")
            assert forbidden not in parts, (
                f"Architectural isolation violation: speech_service.py imports '{mod}', "
                f"which violates the ASR/RAG decoupling invariant."
            )

    for mod, name in names:
        for forbidden in forbidden_patterns:
            parts = mod.split(".")
            assert forbidden not in parts and forbidden != name, (
                f"Architectural isolation violation: speech_service.py imports '{name}' from '{mod}', "
                f"which violates the ASR/RAG decoupling invariant."
            )


def test_ai_package_does_not_import_tts():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Scans every file under ai/ directory and asserts that ZERO files import
    tts, tts_service, or any TTS components.
    ASR/SER must be fully independent of TTS.
    """
    ai_dir = Path("ai")
    assert ai_dir.is_dir(), "ai/ directory must exist"

    ai_py_files = list(ai_dir.rglob("*.py"))
    assert len(ai_py_files) > 0, "ai/ must contain python source files"

    forbidden_patterns = [
        "tts",
        "tts_service",
        "backend.app.services.tts_service",
        "indic_parler",
        "parler_tts",
    ]

    for py_file in ai_py_files:
        modules, names = get_all_python_imports(py_file)

        for mod in modules:
            for forbidden in forbidden_patterns:
                parts = mod.split(".")
                assert forbidden not in parts, (
                    f"Architectural isolation violation: {py_file} imports '{mod}', "
                    f"which violates the ASR/TTS decoupling invariant."
                )

        for mod, name in names:
            for forbidden in forbidden_patterns:
                parts = mod.split(".")
                assert forbidden not in parts and forbidden != name, (
                    f"Architectural isolation violation: {py_file} imports '{name}' from '{mod}', "
                    f"which violates the ASR/TTS decoupling invariant."
                )


def test_speech_service_does_not_import_tts():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Asserts that backend/app/services/speech_service.py does not import TTS.
    Speech perception must NEVER depend on TTS.
    """
    speech_service_path = Path("backend/app/services/speech_service.py")
    assert speech_service_path.is_file(), "speech_service.py must exist"

    modules, names = get_all_python_imports(speech_service_path)
    forbidden_patterns = [
        "tts",
        "tts_service",
        "backend.app.services.tts_service",
        "indic_parler",
        "parler_tts",
    ]

    for mod in modules:
        for forbidden in forbidden_patterns:
            parts = mod.split(".")
            assert forbidden not in parts, (
                f"Architectural isolation violation: speech_service.py imports '{mod}', "
                f"which violates the ASR/TTS decoupling invariant."
            )

    for mod, name in names:
        for forbidden in forbidden_patterns:
            parts = mod.split(".")
            assert forbidden not in parts and forbidden != name, (
                f"Architectural isolation violation: speech_service.py imports '{name}' from '{mod}', "
                f"which violates the ASR/TTS decoupling invariant."
            )


