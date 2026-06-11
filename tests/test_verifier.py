"""Tests du verifier 3-couches (CDC §4.3).

Couvre les cas critiques :
- Couche 1 (structurelle) bloque avant d'appeler la couche 2 ou 3
- Couche 2 (verification_command rc≠0) bloque avant d'appeler la couche 3
- Couche 3 (LLM grader) — verdict false rejette
- Couche 3 — verdict non parsable → verified=false (en cas de doute, on ne valide pas)
- Couche 3 — erreur LLM → verified=false
- Toutes les couches passent → verified=true
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from jarvis.engine.mission.quality_checker import QualityChecker
from jarvis.engine.mission.schemas import Project, Step
from jarvis.engine.mission.verifier import Verifier
from jarvis.providers.llm.base import LLMProvider

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeLLM(LLMProvider):
    """LLM contrôlable : on injecte la réponse brute à renvoyer."""

    def __init__(self, raw: str | None = None, raise_exc: Exception | None = None) -> None:
        self.raw = raw
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_prompt: str | None = None

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        context: str = "",
    ) -> str | AsyncIterator[str]:
        self.calls += 1
        self.last_prompt = messages[-1]["content"] if messages else None
        if self.raise_exc is not None:
            raise self.raise_exc
        assert self.raw is not None
        return self.raw

    async def health_check(self) -> bool:
        return True


async def _fake_cli_success(command: str, timeout: int) -> dict:  # noqa: ARG001, ASYNC109
    return {"success": True, "stdout": "ok", "stderr": "", "returncode": 0}


async def _fake_cli_failure(command: str, timeout: int) -> dict:  # noqa: ARG001, ASYNC109
    return {"success": False, "stdout": "", "stderr": "test failed", "returncode": 1}


async def _fake_cli_raise(command: str, timeout: int) -> dict:  # noqa: ARG001, ASYNC109
    raise RuntimeError("docker not running")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_project_step(
    tmp_path: Path,
    criterion: str = "Le fichier index.html existe.",
    verification_command: str | None = None,
    output: str = "Fichier créé.",
) -> tuple[Project, Step, list[str]]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    project = Project(
        id="proj_test",
        title="Test",
        mission="Mission de test",
        workspace_path=str(workspace),
    )
    step = Step(
        id="s1",
        title="Step",
        description="Description",
        success_criterion=criterion,
        verification_command=verification_command,
        output=output,
    )
    files_before: list[str] = []
    return project, step, files_before


def _verdict_json(verified: bool, issues: list[str] | None = None, notes: str = "") -> str:
    return json.dumps({"verified": verified, "issues": issues or [], "notes": notes})


# ── 1. Couche 1 — structurelle bloque avant les couches suivantes ─────────────


async def test_couche1_fichier_vide_bloque_avant_llm(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(tmp_path, verification_command="true")
    # On crée un fichier vide pour faire échouer la couche 1
    (Path(project.workspace_path) / "vide.py").write_text("")

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_success)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "structural"
    assert llm.calls == 0  # LLM JAMAIS appelé
    assert any("vide" in i.lower() for i in result.issues)


async def test_couche1_python_invalide_bloque(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "bug.py").write_text("def foo(:\n    pass")

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "structural"
    assert llm.calls == 0


# ── 2. Couche 2 — verification_command rc≠0 bloque avant la couche 3 ──────────


async def test_couche2_command_rc_non_nul_bloque_avant_llm(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(
        tmp_path,
        verification_command="pytest -x",  # va échouer (fake renvoie failure)
    )
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_failure)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "deterministic"
    assert llm.calls == 0
    assert any("rc=1" in i for i in result.issues)


async def test_couche2_command_exception_bloque(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(
        tmp_path, verification_command="test something"
    )
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_raise)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "deterministic"
    assert llm.calls == 0


async def test_couche2_absente_passe_directement_a_la_couche3(tmp_path: Path) -> None:
    """Sans verification_command, la couche 2 est sautée."""
    project, step, files_before = _make_project_step(tmp_path, verification_command=None)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_failure)  # serait failure

    result = await verifier.verify(project, step, files_before)
    assert result.verified is True
    assert result.layer == "semantic"
    assert llm.calls == 1


# ── 3. Couche 3 — verdict false rejette ───────────────────────────────────────


async def test_couche3_artefact_compile_mais_ne_repond_pas_au_critere(
    tmp_path: Path,
) -> None:
    """Cas central du §4.3 : un livrable plausible mais faux est rejeté par la couche sémantique."""
    project, step, files_before = _make_project_step(
        tmp_path,
        criterion="Le fichier index.html liste 3 articles.",
    )
    # Fichier qui compile mais ne répond PAS au critère
    (Path(project.workspace_path) / "index.html").write_text("<html><body></body></html>")

    llm = _FakeLLM(
        raw=_verdict_json(
            False,
            issues=["L'index.html est vide, aucun article listé."],
            notes="Le critère exige 3 articles, je n'en trouve 0.",
        ),
    )
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "semantic"
    assert llm.calls == 1
    assert "3 articles" in result.notes


# ── 4. Couche 3 — verdict non parsable → verified=false ──────────────────────


async def test_couche3_verdict_non_parsable_donne_false(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw="Désolé, je ne peux pas évaluer cette tâche.")  # pas du JSON
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "semantic"
    assert any("non parsable" in i for i in result.issues)


async def test_couche3_json_avec_fences_markdown(tmp_path: Path) -> None:
    """Le verifier tolère les ```json ... ``` autour du verdict."""
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw="```json\n" + _verdict_json(True, notes="OK") + "\n```")
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is True


async def test_couche3_json_avec_cles_manquantes_strict(tmp_path: Path) -> None:
    """Si la clé 'verified' n'est pas explicitement True (bool), verified=false."""
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    # verified="True" (string), pas un bool
    llm = _FakeLLM(raw='{"verified": "True", "issues": [], "notes": ""}')
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False  # strict : "True" str ≠ True bool


async def test_couche3_json_array_non_dict(tmp_path: Path) -> None:
    """Un JSON valide mais non-dict → verified=false."""
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw='["verified", true]')
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False


# ── 5. Couche 3 — erreur LLM → verified=false ────────────────────────────────


async def test_couche3_llm_raise_donne_false(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raise_exc=RuntimeError("LLM timeout"))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "semantic"


# ── 6. Toutes les couches passent → verified=true ─────────────────────────────


async def test_toutes_couches_passent_verified_true(tmp_path: Path) -> None:
    project, step, files_before = _make_project_step(
        tmp_path,
        verification_command="ls",
    )
    (Path(project.workspace_path) / "ok.py").write_text("x = 1\n")

    llm = _FakeLLM(raw=_verdict_json(True, notes="Tout est en ordre."))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_success)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is True
    assert result.layer == "semantic"
    assert "ordre" in result.notes


# ── 6bis. Régression — le prompt de couche 3 contient le CONTENU des fichiers ─


async def test_couche3_prompt_contient_contenu_des_fichiers_nouveaux(
    tmp_path: Path,
) -> None:
    """Le grader sémantique a besoin du contenu RÉEL des artefacts pour juger.

    Régression : sans le contenu, le grader refuse à juste titre de se prononcer
    car il ne voit que la liste de fichiers (cas observé sur la mission réelle).
    """
    project, step, files_before = _make_project_step(
        tmp_path,
        criterion="Le fichier index.html contient 3 articles d'astronomie.",
    )
    contenu = (
        "<!DOCTYPE html><html><body>"
        "<article><h2>Exoplanètes</h2><p>...</p></article>"
        "<article><h2>Trous noirs</h2><p>...</p></article>"
        "<article><h2>Pulsars</h2><p>...</p></article>"
        "</body></html>"
    )
    (Path(project.workspace_path) / "index.html").write_text(contenu)

    llm = _FakeLLM(raw=_verdict_json(True, notes="Trois articles trouvés."))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is True

    # Le prompt doit inclure le contenu, pas juste le nom
    assert llm.last_prompt is not None
    assert "Exoplanètes" in llm.last_prompt
    assert "Trous noirs" in llm.last_prompt
    assert "Pulsars" in llm.last_prompt
    assert "=== index.html" in llm.last_prompt


async def test_couche3_prompt_tronque_au_dela_de_la_limite(tmp_path: Path) -> None:
    """Si un fichier dépasse _MAX_CONTENT_CHARS, le prompt le tronque proprement."""
    project, step, files_before = _make_project_step(tmp_path)
    # Fichier de 20 000 chars (au-dessus de _MAX_CONTENT_CHARS = 6000)
    enorme = "x" * 20000
    (Path(project.workspace_path) / "huge.txt").write_text(enorme)

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    await verifier.verify(project, step, files_before)
    assert llm.last_prompt is not None
    # Le prompt ne doit pas contenir les 20 000 chars
    assert "tronqué" in llm.last_prompt
    assert llm.last_prompt.count("x") < 8000  # marge pour le reste du prompt


async def test_couche3_binaire_skip(tmp_path: Path) -> None:
    """Les fichiers binaires (png, jpg) sont mentionnés mais leur contenu n'est pas lu."""
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    llm = _FakeLLM(raw=_verdict_json(True))
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm)

    await verifier.verify(project, step, files_before)
    assert llm.last_prompt is not None
    assert "img.png" in llm.last_prompt
    assert "binaire" in llm.last_prompt


# ── 7. Garde-fou supplémentaire : la couche structurelle n'appelle JAMAIS le LLM


@pytest.mark.parametrize(
    "raw_response",
    [_verdict_json(True), "garbage", ""],  # peu importe ce que le LLM aurait dit
)
async def test_couche1_court_circuit_complet(tmp_path: Path, raw_response: str) -> None:
    project, step, files_before = _make_project_step(tmp_path)
    (Path(project.workspace_path) / "vide.py").write_text("")  # déclenche couche 1

    llm = _FakeLLM(raw=raw_response or "should not be called")
    quality = QualityChecker(project.workspace_path)
    verifier = Verifier(quality, llm, cli_executor=_fake_cli_success)

    result = await verifier.verify(project, step, files_before)
    assert result.verified is False
    assert result.layer == "structural"
    assert llm.calls == 0
