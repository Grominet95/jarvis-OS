"""Skill Lab (CDC §7) — génération + test sandbox + cycle de vie.

Pipeline complète :
  signal `skill_candidate_proposal` (PHASE 2)
    → SkillLab.propose_from_event(event_id)
    → SkillSynthesizer.propose_skill_candidate(trajectory) (zone tampon)
    → SkillLab.test_in_sandbox(name) (test générique en Docker)
    → si test vert : status SANDBOXED_PASS, attend validation humaine
    → si test rouge : status SANDBOXED_FAIL (REJET AUTOMATIQUE, audit)
    → après validation humaine : SkillLab.promote(name) → ACTIVE,
      déplace candidates/{name}/ → installed/{name}/, reload SkillRegistry

GATE TEST-VERT-SINON-REJET : c'est le cœur dur de la phase. Une skill qui
échoue son test sandbox n'est JAMAIS installée. C'est l'analogue de la couche
sémantique du verifier PHASE 1.

Le test sandbox est GÉNÉRIQUE (décision Q-D=a) :
  1. Le fichier skill.py s'importe sans erreur.
  2. La classe (subclass de SkillBase) s'instancie sans crash.
  3. `get_system_prompt()` retourne une chaîne non-vide.
  4. (Si get_tools() retourne) chaque tool a `name`, `description`,
     `input_schema` valides.

Aucune skill ne modifie le core (CDC §7 anti-patterns) — la sandbox Docker
isole tout effet de bord. Le test est read-only sur /workspace.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from jarvis.capabilities.skills.lifecycle import SkillLifecycle, SkillRecord, SkillStatus
from jarvis.capabilities.skills.synthesizer import (
    SKILLS_CANDIDATES_DIR,
    SKILLS_INSTALLED_DIR,
    SkillSynthesizer,
)
from jarvis.engine.mission.docker_executor import DockerExecutor
from jarvis.kernel.contracts import MemoryStore as MemoryKernel
from jarvis.kernel.paths import PROJECT_ROOT
from jarvis.kernel.settings import settings

# Plafond du nombre d'events skill_candidate_proposal traités par scan.
_MAX_EVENTS_PER_SCAN = 20
# Plafond du nombre de skills générées par scan (cap dur sur les appels LLM).
_MAX_CANDIDATES_PER_SCAN = 5
# Timeout (s) du test sandbox dans Docker.
_SANDBOX_TIMEOUT = 30


# ── Résultats ─────────────────────────────────────────────────────────────────


@dataclass
class SandboxTestResult:
    """Verdict du test sandbox d'une skill candidate."""

    passed: bool
    layer_failed: str  # "import" | "instantiate" | "system_prompt" | "tools" | "ok"
    notes: str


@dataclass
class LabScanResult:
    """Trace d'un scan polling (run du Lab sur le Kernel)."""

    events_examined: int
    candidates_generated: int
    sandbox_passed: int
    sandbox_failed: int
    skipped_already_handled: int
    errors: list[str]


# ── Test générique sandbox ────────────────────────────────────────────────────

# Script Python générique exécuté dans la sandbox. Importé puis joué avec
# `python /workspace/_skill_sandbox_test.py`. Exit 0 = test vert.
_SANDBOX_TEST_SCRIPT = textwrap.dedent(
    '''
    """Test générique d'une skill candidate. Exit 0 si tout passe, ≠ 0 sinon."""

    import importlib.util
    import json
    import sys
    import traceback
    from pathlib import Path

    SKILL_DIR = Path("/workspace/candidate")
    SKILL_PY = SKILL_DIR / "skill.py"
    SKILL_YAML = SKILL_DIR / "skill.yaml"


    def _fail(layer: str, message: str) -> None:
        sys.stdout.write(json.dumps({"layer": layer, "ok": False, "notes": message}))
        sys.exit(1)


    def _ok(layer: str, message: str = "") -> None:
        sys.stdout.write(json.dumps({"layer": layer, "ok": True, "notes": message}))


    # 1) Rendre `skills.base` résolvable AVANT d'importer skill.py — la
    # candidate fait `from skills.base import SkillBase` au top, donc le
    # sys.path doit déjà contenir la racine du repo. (Ce sys.path.insert
    # arrivait après exec_module dans une version antérieure ; tous les
    # skills réels étaient alors rejetés à la couche import.)
    sys.path.insert(0, "/jarvis_src")
    try:
        from jarvis.capabilities.skills.base import SkillBase  # lazy: sandbox path
    except Exception as exc:
        _fail("import", f"SkillBase indisponible dans la sandbox : {exc!r}")


    # 2) Import du skill.py de la candidate.
    if not SKILL_PY.exists():
        _fail("import", f"skill.py introuvable dans {SKILL_DIR}")

    try:
        spec = importlib.util.spec_from_file_location("candidate_skill", SKILL_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        _fail("import", f"import a échoué : {exc!r}\\n{traceback.format_exc()[:600]}")

    skill_class = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, SkillBase)
            and attr is not SkillBase
            and attr.__module__ == module.__name__
        ):
            skill_class = attr
            break

    if skill_class is None:
        _fail("import", "aucune classe SkillBase trouvée dans skill.py")


    # 3) Charger les métadonnées si présentes
    metadata = {}
    if SKILL_YAML.exists():
        try:
            import yaml
            with SKILL_YAML.open() as f:
                metadata = yaml.safe_load(f) or {}
        except Exception as exc:
            _fail("import", f"skill.yaml illisible : {exc!r}")


    # 4) Instancier la classe
    try:
        skill = skill_class(metadata=metadata)
    except Exception as exc:
        _fail("instantiate", f"instantiation a échoué : {exc!r}")


    # 5) get_system_prompt() retourne une chaîne non-vide
    try:
        prompt = skill.get_system_prompt()
    except Exception as exc:
        _fail("system_prompt", f"get_system_prompt() a levé : {exc!r}")

    if not isinstance(prompt, str) or not prompt.strip():
        _fail("system_prompt", f"get_system_prompt() doit retourner str non-vide, "
              f"reçu {type(prompt).__name__} de longueur {len(prompt or '')}")


    # 6) Si get_tools() retourne quelque chose, chaque tool doit être valide
    try:
        tools = skill.get_tools()
    except Exception as exc:
        _fail("tools", f"get_tools() a levé : {exc!r}")

    if tools:
        for i, tool in enumerate(tools):
            for attr in ("name", "description", "input_schema"):
                if not hasattr(tool, attr):
                    _fail("tools", f"tool[{i}] manque l'attribut '{attr}'")
            if not isinstance(tool.name, str) or not tool.name.strip():
                _fail("tools", f"tool[{i}].name doit être str non-vide")
            if not isinstance(tool.description, str) or not tool.description.strip():
                _fail("tools", f"tool[{i}].description doit être str non-vide")
            if not isinstance(tool.input_schema, dict):
                _fail("tools", f"tool[{i}].input_schema doit être dict")


    _ok("ok", f"skill '{skill.name}' validée (prompt={len(prompt)} chars, "
        f"tools={len(tools)})")
    '''
).strip()


# ── Lab ───────────────────────────────────────────────────────────────────────


class SkillLab:
    """Pilote du cycle Génération → Sandbox → Validation humaine → Installation.

    Le Lab ne stocke pas d'état lui-même : il lit/écrit le SkillLifecycle (SQL)
    et manipule les dossiers sur disque (candidates/ ↔ installed/).
    """

    def __init__(
        self,
        kernel: MemoryKernel,
        lifecycle: SkillLifecycle,
        synthesizer: SkillSynthesizer,
        *,
        candidates_dir: Path = SKILLS_CANDIDATES_DIR,
        installed_dir: Path = SKILLS_INSTALLED_DIR,
        registry_reload: callable | None = None,
    ) -> None:
        self._kernel = kernel
        self._lifecycle = lifecycle
        self._synthesizer = synthesizer
        self._candidates_dir = Path(candidates_dir)
        self._installed_dir = Path(installed_dir)
        # Callable optionnel pour recharger le SkillRegistry après promotion.
        # Injecté par main.py via skill_registry.reload.
        self._registry_reload = registry_reload

    # ── Polling Kernel ────────────────────────────────────────────────────────

    async def scan_kernel(self) -> LabScanResult:
        """Scanne les events `skill_candidate_proposal` non encore traités et
        déclenche la pipeline pour chacun.

        Idempotent : `lifecycle.has_been_proposed_for_event(event_id)` évite de
        re-générer pour un event déjà vu. Cap dur sur le nombre d'events
        examinés (`_MAX_EVENTS_PER_SCAN`) et de candidates générées
        (`_MAX_CANDIDATES_PER_SCAN`) pour borner les appels LLM.
        """
        result = LabScanResult(
            events_examined=0,
            candidates_generated=0,
            sandbox_passed=0,
            sandbox_failed=0,
            skipped_already_handled=0,
            errors=[],
        )

        events = self._fetch_skill_candidate_events(limit=_MAX_EVENTS_PER_SCAN)
        result.events_examined = len(events)

        for event in events:
            if result.candidates_generated >= _MAX_CANDIDATES_PER_SCAN:
                logger.info(
                    "SkillLab: cap appels LLM atteint",
                    cap=_MAX_CANDIDATES_PER_SCAN,
                )
                break
            event_id = event["id"]
            if self._lifecycle.has_been_proposed_for_event(event_id):
                result.skipped_already_handled += 1
                continue
            try:
                outcome = await self.propose_from_event(event_id, event)
                result.candidates_generated += 1
                if outcome and outcome.status == SkillStatus.SANDBOXED_PASS:
                    result.sandbox_passed += 1
                elif outcome and outcome.status == SkillStatus.SANDBOXED_FAIL:
                    result.sandbox_failed += 1
            except Exception as exc:  # noqa: BLE001 — best-effort par event
                logger.warning(
                    "SkillLab: scan échec sur event",
                    event_id=event_id,
                    error=str(exc),
                )
                result.errors.append(f"{event_id}: {exc}")

        logger.info(
            "SkillLab scan terminé",
            examined=result.events_examined,
            generated=result.candidates_generated,
            passed=result.sandbox_passed,
            failed=result.sandbox_failed,
            skipped=result.skipped_already_handled,
            errors=len(result.errors),
        )
        return result

    def _fetch_skill_candidate_events(self, limit: int) -> list[dict]:
        """Récupère les N events `skill_candidate_proposal` les plus récents.

        Retourne des dicts {id, content, metadata_json, created_at}.
        """
        import sqlite3

        with sqlite3.connect(self._kernel.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, content, metadata_json, created_at "
                "FROM events WHERE type = ? "
                "ORDER BY created_at DESC LIMIT ?",
                ("skill_candidate_proposal", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Pipeline depuis un event ──────────────────────────────────────────────

    async def propose_from_event(
        self, event_id: str, event_payload: dict | None = None
    ) -> SkillRecord | None:
        """Pipeline complète depuis un event Kernel `skill_candidate_proposal`.

        Wrapper qui fetch l'event, le convertit en trajectoire, puis délègue à
        `propose_from_trajectory(trajectory, source_event_id=event_id)`.
        """
        if event_payload is None:
            evt = self._kernel.get_event(event_id)
            if evt is None:
                logger.warning("SkillLab: event introuvable", event_id=event_id)
                return None
            event_payload = {
                "id": evt.id,
                "content": evt.content,
                "metadata_json": evt.metadata_json,
            }
        trajectory = self._event_to_trajectory(event_payload)
        return await self.propose_from_trajectory(trajectory, source_event_id=event_id)

    async def propose_from_trajectory(
        self,
        trajectory: dict,
        source_event_id: str | None = None,
    ) -> SkillRecord | None:
        """API publique : pipeline depuis une trajectoire arbitraire (tool, signal).

        C'est le SEUL point d'entrée pour créer une skill candidate. Aucun
        chemin alternatif ne doit court-circuiter ce gate (cf. CDC §7.3 anti-
        pattern : "Ne pas installer une skill sans test vert en sandbox").

        Étapes :
        1. Génère la skill candidate via le synthesizer (écrit dans
           candidates_dir/{name}/ — ZONE TAMPON, pas installed/).
        2. Enregistre la candidate dans le lifecycle SQL (source_event_id pour
           idempotence du polling).
        3. Test sandbox → SANDBOXED_PASS ou SANDBOXED_FAIL.
        4. Renvoie le SkillRecord final, ou None si la génération a échoué.

        La promotion vers installed/ exige une action humaine explicite via
        SkillLab.promote() (typiquement endpoint POST /api/skills/lab/{name}/promote).
        """
        # 1) Génère la candidate dans la zone tampon (jamais dans installed/).
        try:
            skill_name = await self._synthesizer.propose_skill_candidate(
                trajectory, target_dir=self._candidates_dir
            )
        except Exception as exc:  # noqa: BLE001 — synthèse foireuse, on log
            logger.warning(
                "SkillLab: génération candidate échouée",
                source_event_id=source_event_id,
                error=str(exc),
            )
            return None

        # 2) Enregistre dans le lifecycle (status=CANDIDATE par défaut).
        self._lifecycle.create_candidate(name=skill_name, source_event_id=source_event_id)

        # 3) Test sandbox — le gate critique.
        return await self.test_in_sandbox(skill_name)

    @staticmethod
    def _event_to_trajectory(event_payload: dict) -> dict:
        """Convertit un event skill_candidate_proposal en trajectoire pour le synthesizer."""
        meta: dict = {}
        if event_payload.get("metadata_json"):
            try:
                meta = json.loads(event_payload["metadata_json"]) or {}
            except (TypeError, json.JSONDecodeError):
                pass
        return {
            "task_description": event_payload.get("content", "")[:600],
            "result": meta.get("from_lesson_evt", ""),
            "messages": [],
            "tool_calls": [],
        }

    # ── Test sandbox (gate test-vert-sinon-rejet) ────────────────────────────

    async def test_in_sandbox(self, skill_name: str) -> SkillRecord | None:
        """Lance le test générique en sandbox Docker. Met à jour le lifecycle.

        Si Docker indisponible → fallback exécution directe avec ATTENTION
        loguée. C'est le compromis du MVP : sans Docker, on garde un test
        déterministe utile (l'isolation est moins forte).
        """
        cand_dir = self._candidates_dir / skill_name
        if not (cand_dir / "skill.py").exists():
            logger.warning("SkillLab: candidate introuvable", name=skill_name)
            return None

        try:
            result = await self._run_sandbox_test(cand_dir)
        except Exception as exc:  # noqa: BLE001
            result = SandboxTestResult(
                passed=False,
                layer_failed="sandbox_error",
                notes=f"Erreur infrastructure sandbox : {exc!r}",
            )

        record = self._lifecycle.mark_sandbox_result(
            name=skill_name,
            passed=result.passed,
            notes=f"[{result.layer_failed}] {result.notes}",
        )
        logger.info(
            "SkillLab sandbox",
            name=skill_name,
            passed=result.passed,
            layer=result.layer_failed,
        )
        return record

    async def _run_sandbox_test(self, cand_dir: Path) -> SandboxTestResult:
        """Crée un container Docker temporaire, monte candidates/{name}/
        en read-only, exécute le test générique, parse la sortie JSON."""

        if not settings.docker_enabled:
            return await self._run_direct_test(cand_dir)

        # Vérifie que Docker est joignable
        if not await DockerExecutor.is_available():
            logger.warning(
                "SkillLab: Docker indisponible, fallback test direct",
                cand_dir=str(cand_dir),
            )
            return await self._run_direct_test(cand_dir)

        # Container ad-hoc : workspace tmpfs + candidate montée RO + source jarvis montée RO
        container_name = f"jarvis-skill-lab-{uuid.uuid4().hex[:8]}"
        cand_abs = cand_dir.resolve()
        jarvis_root = PROJECT_ROOT

        # Crée le script de test dans un tmpdir local et le mount aussi
        script_path = cand_abs / "_skill_sandbox_test.py"
        script_path.write_text(_SANDBOX_TEST_SCRIPT, encoding="utf-8")

        try:
            cmd = [
                "docker",
                "run",
                "--rm",
                "--name",
                container_name,
                f"--memory={settings.docker_memory_limit}",
                f"--cpus={settings.docker_cpu_limit}",
                "--network",
                "none",  # pas de réseau pour le test sandbox
                "--read-only",
                "--tmpfs",
                "/tmp:rw,size=50m",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "-v",
                f"{cand_abs}:/workspace/candidate:ro",
                "-v",
                f"{jarvis_root}:/jarvis_src:ro",
                "-w",
                "/workspace",
                settings.docker_base_image,
                "python",
                "/workspace/candidate/_skill_sandbox_test.py",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=_SANDBOX_TIMEOUT
                )
            except TimeoutError:
                # Tue le container
                killer = await asyncio.create_subprocess_exec(
                    "docker",
                    "kill",
                    container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.communicate()
                return SandboxTestResult(
                    passed=False,
                    layer_failed="timeout",
                    notes=f"timeout après {_SANDBOX_TIMEOUT}s",
                )
        finally:
            script_path.unlink(missing_ok=True)

        return self._parse_sandbox_output(proc.returncode, stdout, stderr)

    async def _run_direct_test(self, cand_dir: Path) -> SandboxTestResult:
        """Fallback : exécute le test dans un subprocess Python local (pas Docker).

        Moins isolé qu'une vraie sandbox mais préserve le gate test-vert
        comme garde-fou MVP quand Docker n'est pas disponible (typique en CI
        ou en dev local sans Docker daemon).
        """
        cand_abs = cand_dir.resolve()
        jarvis_root = PROJECT_ROOT
        script_path = cand_abs / "_skill_sandbox_test.py"
        # Remplace /workspace/candidate par cand_abs et /jarvis_src par jarvis_root
        # On crée un script adapté au mode direct.
        direct_script = _SANDBOX_TEST_SCRIPT.replace(
            'Path("/workspace/candidate")', f'Path(r"{cand_abs}")'
        ).replace('"/jarvis_src"', f'r"{jarvis_root}"')
        script_path.write_text(direct_script, encoding="utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=_SANDBOX_TIMEOUT
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxTestResult(
                    passed=False,
                    layer_failed="timeout",
                    notes=f"timeout après {_SANDBOX_TIMEOUT}s (direct)",
                )
        finally:
            script_path.unlink(missing_ok=True)

        return self._parse_sandbox_output(proc.returncode, stdout, stderr)

    @staticmethod
    def _parse_sandbox_output(
        returncode: int | None,
        stdout: bytes,
        stderr: bytes,
    ) -> SandboxTestResult:
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            return SandboxTestResult(
                passed=False,
                layer_failed="parse",
                notes=(
                    f"sortie sandbox non-JSON (rc={returncode}): "
                    f"stdout={out[:200]!r} stderr={err[:200]!r}"
                ),
            )
        if not isinstance(payload, dict):
            return SandboxTestResult(
                passed=False,
                layer_failed="parse",
                notes=f"payload non-dict : {payload!r}",
            )
        ok = bool(payload.get("ok"))
        layer = str(payload.get("layer", "?"))
        notes = str(payload.get("notes", ""))[:600]
        if not ok and not notes:
            notes = err[:400] or out[:400]
        return SandboxTestResult(passed=ok, layer_failed=layer, notes=notes)

    # ── Promotion / Rejet ────────────────────────────────────────────────────

    def promote(self, skill_name: str) -> SkillRecord | None:
        """Validation humaine accordée : déplace candidate → installed,
        marque ACTIVE dans le lifecycle, recharge le SkillRegistry.

        Refuse si la skill n'est pas en SANDBOXED_PASS — on n'installe JAMAIS
        une skill qui n'a pas passé son test sandbox (CDC §7 anti-pattern :
        "Ne pas installer une skill sans test vert en sandbox").
        """
        record = self._lifecycle.get(skill_name)
        if record is None:
            logger.warning("SkillLab.promote: skill inconnue", name=skill_name)
            return None
        if record.status != SkillStatus.SANDBOXED_PASS:
            logger.warning(
                "SkillLab.promote: refusé — status non SANDBOXED_PASS",
                name=skill_name,
                status=record.status.value,
            )
            return None

        cand_dir = self._candidates_dir / skill_name
        installed_dir = self._installed_dir / skill_name
        if not cand_dir.exists():
            logger.error("SkillLab.promote: candidate disparue du disque", name=skill_name)
            return None
        if installed_dir.exists():
            # Collision : on refuse plutôt que d'écraser une skill installée
            logger.error(
                "SkillLab.promote: collision avec skill installée",
                name=skill_name,
            )
            return None

        installed_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cand_dir), str(installed_dir))
        # Nettoie le fichier test résiduel s'il existe
        (installed_dir / "_skill_sandbox_test.py").unlink(missing_ok=True)

        promoted = self._lifecycle.promote(skill_name)

        if self._registry_reload is not None:
            try:
                self._registry_reload()
            except Exception as exc:  # noqa: BLE001
                logger.warning("SkillRegistry.reload() échec", error=str(exc))

        logger.info("Skill promue et installée", name=skill_name)
        return promoted

    def reject(
        self,
        skill_name: str,
        reason: str = "",
        delete_files: bool = False,
    ) -> SkillRecord | None:
        """Validation humaine refusée : marque REJECTED dans le lifecycle.

        delete_files=False par défaut → la candidate reste sur disque (audit).
        delete_files=True → supprime physiquement le dossier candidates/{name}/.
        """
        record = self._lifecycle.reject(skill_name, reason=reason)
        if delete_files:
            cand_dir = self._candidates_dir / skill_name
            if cand_dir.exists():
                shutil.rmtree(cand_dir)
                logger.info("SkillLab: candidate supprimée du disque", name=skill_name)
        return record


__all__ = [
    "LabScanResult",
    "SandboxTestResult",
    "SkillLab",
]
