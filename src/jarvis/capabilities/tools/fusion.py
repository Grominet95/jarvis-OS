"""
Outil Fusion 360 pour Jarvis — Autodesk MCP HTTP (port 27182).

API réelle (3 outils) :
  fusion_mcp_execute  → exécuter un script Python Fusion API
  fusion_mcp_read     → lire (screenshot, documents, projets, doc API)
  fusion_mcp_update   → undo / redo
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from loguru import logger

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.approval import get_approval_checker
from jarvis.kernel.settings import settings


class _FusionClient:
    """Client MCP HTTP minimal pour Fusion 360."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._req_id = 0

    @property
    def url(self) -> str:
        return settings.fusion_mcp_url

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _post(self, method: str, params: dict[str, Any]) -> dict:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}

        async with httpx.AsyncClient() as client:
            r = await client.post(self.url, json=payload, headers=headers, timeout=30)

        if sid := r.headers.get("Mcp-Session-Id"):
            self._session_id = sid

        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return _parse_sse(r.text)
        return r.json()

    async def initialize(self) -> bool:
        try:
            resp = await self._post(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "jarvis", "version": "3.0"},
                },
            )
            return "result" in resp
        except Exception:
            return False

    async def call(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """Appelle un outil MCP et retourne (success, text)."""
        resp = await self._post("tools/call", {"name": tool_name, "arguments": arguments})

        if "error" in resp:
            err = resp["error"]
            return False, err.get("message", str(err)) if isinstance(err, dict) else str(err)

        content = resp.get("result", {}).get("content", [])
        if isinstance(content, list) and content:
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return True, "\n".join(filter(None, texts)) or str(content)
        return True, "OK"


def _parse_sse(body: str) -> dict:
    import json

    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except Exception:
                pass
    return {}


_client = _FusionClient()


def _wrap_script(user_script: str) -> str:
    """
    Enveloppe le script utilisateur pour capturer succès/erreur via print().
    Le MCP retourne le stdout du script — on s'en sert comme feedback.
    """
    # Si le script contient déjà print("FUSION_OK") ou FUSION_ERROR → ne pas re-wrapper
    if "FUSION_OK" in user_script or "FUSION_ERROR" in user_script:
        return user_script

    # Extraire le corps de run(context) et le réinjecter avec gestion d'erreur
    return f"""
import adsk.core, adsk.fusion, traceback as _tb

{user_script}

_orig_run = run

def run(context):
    try:
        _orig_run(context)
        print("FUSION_OK: script exécuté avec succès")
    except Exception as _e:
        print("FUSION_ERROR: " + _tb.format_exc())
"""


class FusionTool(Tool):
    name = "fusion_360"
    description = """
Contrôle Autodesk Fusion 360 via l'API MCP officielle.
Fusion 360 doit être ouvert avec le serveur MCP activé (port 27182).

=== 3 ACTIONS DISPONIBLES ===

1. execute_script — Exécuter un script Python Fusion API pour créer/modifier la géométrie.
   Le script doit être complet, autonome, utiliser adsk.core / adsk.fusion.
   TOUJOURS inclure def run(context): et le code dans ce bloc.

2. read — Lire depuis Fusion 360 :
   - query_type="screenshot" : capturer la vue actuelle
   - query_type="document" : lister/chercher les documents
   - query_type="projects" : lister les projets
   - query_type="apiDocumentation" : chercher dans la doc API

3. undo / redo — Annuler ou refaire la dernière action.

=== EXEMPLE — créer un cube 3×3×3 cm ===

action="execute_script", script=\"\"\"
import adsk.core, adsk.fusion, traceback

def run(context):
    try:
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(3, 3, 0)
        )
        ext_input = root.features.extrudeFeatures.createInput(
            sketch.profiles.item(0),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(3))
        root.features.extrudeFeatures.add(ext_input)
    except:
        adsk.core.Application.get().userInterface.messageBox(traceback.format_exc())
\"\"\"

NOTE: Fusion 360 utilise les centimètres en interne.
  - 3 cm → createByReal(3)
  - 30 mm → createByReal(3) aussi (toujours en cm)

RÈGLE CRITIQUE — document actif (obligatoire en début de chaque script) :
  for doc in app.documents:
      try:
          if doc.documentType == adsk.core.DocumentTypes.FusionDesignDocumentType:
              d = adsk.fusion.Design.cast(doc.product)
              if d and d.rootComponent.bRepBodies.count > 0:
                  if not doc.isActive: doc.activate()
                  break
      except: pass
  # JAMAIS app.documents.add() — crée un fichier vide à chaque appel !
  # Si aucun body trouvé, travailler sur l'actif (normal en début de projet)
  design = adsk.fusion.Design.cast(app.activeProduct); root = design.rootComponent

INTERDIT (provoque RuntimeError) :
  - root.name = "..." ou rootComponent.name = "..." → lecture seule
  - root.occurrences.addNewComponent(...) → interdit (mode Part, pas Assemblage)
  - Pour nommer : body.name = "MonNom" sur BRepBody uniquement
Shell : top_face = max(body.faces, key=lambda f: f.centroid.z); jamais par index.
Cut (CutFeatureOperation) : "Aucun corps cible" = sketch sur mauvais plan
  ou participantBodies absent.
  body = root.bRepBodies.item(0)
  face = max(body.faces, key=lambda f: f.centroid.z)   # sketch sur la face du body
  sketch = root.sketches.add(face)                      # PAS sur xYConstructionPlane
  inp = root.features.extrudeFeatures.createInput(sketch.profiles.item(0),
        adsk.fusion.FeatureOperations.CutFeatureOperation)
  inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(-depth))
  col = adsk.core.ObjectCollection.create(); col.add(body)
  inp.participantBodies = col                           # OBLIGATOIRE pour les Cut
  root.features.extrudeFeatures.add(inp)
"""

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["execute_script", "read", "undo", "redo"],
                "description": "Action à effectuer dans Fusion 360",
            },
            "script": {
                "type": "string",
                "description": (
                    "Script Python Fusion API complet (requis pour execute_script)."
                    " Doit contenir def run(context):"
                ),
            },
            "query_type": {
                "type": "string",
                "enum": ["screenshot", "document", "projects", "apiDocumentation"],
                "description": "Type de lecture (requis pour read)",
            },
            "direction": {
                "type": "string",
                "enum": [
                    "current",
                    "front",
                    "back",
                    "top",
                    "bottom",
                    "left",
                    "right",
                    "iso-top-right",
                ],
                "description": "Direction caméra pour screenshot (défaut: current)",
            },
            "name": {
                "type": "string",
                "description": "Terme de recherche pour query_type=document",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: str,
        script: str = "",
        query_type: str = "screenshot",
        direction: str = "current",
        name: str = "",
        **_: object,
    ) -> ToolResult:
        if not settings.fusion_enabled:
            return ToolResult(
                content="Fusion 360 est désactivé (FUSION_ENABLED=false dans .env).",
                is_error=True,
            )

        # Approbation pour les scripts (modifications)
        if action == "execute_script":
            checker = get_approval_checker()
            if checker:
                ok = await checker.check(
                    "fusion_create",
                    f"Exécuter script Fusion 360: {script[:80]}...",
                    str(uuid.uuid4())[:8],
                )
                if not ok:
                    return ToolResult(content="Script Fusion refusé.", is_error=True)

        return await self._dispatch(action, script, query_type, direction, name)

    async def _dispatch(
        self,
        action: str,
        script: str,
        query_type: str,
        direction: str,
        name: str,
    ) -> ToolResult:
        global _client

        # Initialiser la session si nécessaire
        if not _client._session_id:
            ok = await _client.initialize()
            if not ok:
                _client = _FusionClient()
                ok = await _client.initialize()
                if not ok:
                    return ToolResult(
                        content=f"Fusion 360 MCP inaccessible (port {settings.fusion_mcp_port}). "
                        "Vérifier que Fusion est ouvert.",
                        is_error=True,
                    )

        try:
            if action == "execute_script":
                if not script:
                    return ToolResult(content="script requis pour execute_script", is_error=True)
                ok, result = await _client.call(
                    "fusion_mcp_execute",
                    {
                        "featureType": "script",
                        "object": {"script": _wrap_script(script)},
                    },
                )
                # Détecter les erreurs dans le résultat
                if ok and "FUSION_ERROR:" in result:
                    return ToolResult(
                        content=result.replace("FUSION_ERROR:", "Erreur Fusion:"), is_error=True
                    )
                return ToolResult(content=result or "Script exécuté.", is_error=not ok)

            elif action == "read":
                args: dict[str, Any] = {"queryType": query_type}
                if query_type == "screenshot":
                    args["direction"] = direction
                elif query_type == "document" and name:
                    args["operation"] = "search"
                    args["name"] = name
                ok, result = await _client.call("fusion_mcp_read", args)
                return ToolResult(content=result, is_error=not ok)

            elif action in ("undo", "redo"):
                ok, result = await _client.call("fusion_mcp_update", {"featureType": action})
                return ToolResult(content=result, is_error=not ok)

            return ToolResult(content=f"Action inconnue: {action}", is_error=True)

        except httpx.ConnectError:
            _client._session_id = None
            return ToolResult(
                content=f"Connexion perdue avec Fusion 360 MCP (port {settings.fusion_mcp_port}).",
                is_error=True,
            )
        except Exception as e:
            logger.error(f"Fusion 360 error: {e}")
            return ToolResult(content=str(e), is_error=True)
