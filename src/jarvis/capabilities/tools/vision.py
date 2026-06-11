from __future__ import annotations

import asyncio
import base64
import io
import platform
import subprocess

from loguru import logger
from openai import AsyncOpenAI
from PIL import Image, ImageGrab

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.contracts import VisualMemory
from jarvis.kernel.permissions import permissions as _perms
from jarvis.kernel.settings import settings


class VisionTool(Tool):
    """Capture et analyse une frame webcam ou écran via GPT-4o Vision.

    Règle absolue : aucune frame n'est jamais écrite sur le disque.
    Tout transit en RAM (bytes) : capturé → encodé base64 → envoyé → oublié.
    """

    name = "vision"
    description = (
        "Capture et analyse une image depuis la webcam ou l'écran via GPT-4o Vision. "
        "Actions disponibles :\n"
        "- 'snapshot' (défaut) : capture + question libre (usage général). "
        "Utilise quand l'utilisateur dit : 'regarde', 'tu vois ça ?', 'décris ce que tu vois'.\n"
        "- 'read_document' : extrait et transcrit le texte d'un document physique "
        "(livre, facture, datasheet, note manuscrite). "
        "Utilise quand l'utilisateur dit : 'lis ça', 'qu'est-ce qu'il y a écrit'.\n"
        "- 'analyze_schema' : analyse un schéma électronique, PCB ou diagramme. "
        "Utilise quand l'utilisateur dit : 'regarde ce schéma', 'analyse ce PCB'.\n"
        "- 'recall' : retrouve un souvenir visuel passé dans la mémoire. "
        "Utilise quand l'utilisateur dit : 'tu te souviens de ce que tu avais vu ?', "
        "'le schéma que je t'avais montré'. Dans ce cas, source n'est pas requis."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["snapshot", "read_document", "analyze_schema", "recall"],
                "description": "Action à effectuer. Défaut: 'snapshot'.",
            },
            "source": {
                "type": "string",
                "enum": ["webcam", "screen"],
                "description": (
                    "Source de la capture. 'webcam' pour la caméra,"
                    " 'screen' pour l'écran. Non requis pour 'recall'."
                ),
            },
            "question": {
                "type": "string",
                "description": (
                    "Question précise à poser sur l'image ou terme de recherche pour 'recall'. "
                    "Ex: 'Y a-t-il des erreurs dans ce code ?'"
                ),
            },
            "detail": {
                "type": "string",
                "enum": ["low", "high"],
                "description": (
                    "Niveau de détail. 'high' pour code/texte fin. Défaut: 'low'"
                    " (forcé 'high' pour read_document et analyze_schema)."
                ),
            },
        },
        "required": ["question"],
    }

    def __init__(self, visual_memory: VisualMemory) -> None:
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._visual_memory = visual_memory

    async def execute(
        self,
        question: str,
        action: str = "snapshot",
        source: str = "webcam",
        detail: str = "low",
        **_: object,
    ) -> ToolResult:

        # ── Recall — pas de capture ───────────────────────────────────────────
        if action == "recall":
            matches = await self._visual_memory.search(question)
            if matches:
                return ToolResult(
                    content="Voici ce dont je me souviens :\n\n" + "\n\n---\n\n".join(matches)
                )
            return ToolResult(content="Je n'ai pas de souvenir visuel correspondant à ta demande.")

        # ── Capture ───────────────────────────────────────────────────────────
        if source == "webcam" and not _perms.get("camera"):
            return ToolResult(content="Caméra désactivée dans les permissions.", is_error=True)
        if source == "screen" and not _perms.get("screen"):
            return ToolResult(
                content="Capture d'écran désactivée dans les permissions.", is_error=True
            )

        loop = asyncio.get_running_loop()

        if source == "webcam":
            jpeg_bytes = await loop.run_in_executor(None, self._capture_webcam)
        elif source == "screen":
            jpeg_bytes = await loop.run_in_executor(None, self._capture_screen)
        else:
            return ToolResult(
                content=f"Source inconnue: '{source}'. Utilise 'webcam' ou 'screen'.",
                is_error=True,
            )

        if not jpeg_bytes:
            return ToolResult(
                content=(
                    "Capture échouée — webcam indisponible ou écran inaccessible. "
                    "Vérifie : Préférences Système → Confidentialité → Caméra / Enreg. écran."
                ),
                is_error=True,
            )

        # ── Paramètres selon l'action ─────────────────────────────────────────
        if action in ("read_document", "analyze_schema"):
            detail = "high"

        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        logger.debug(
            "Vision capture", action=action, source=source, size_kb=round(len(jpeg_bytes) / 1024, 1)
        )

        prompt = self._build_prompt(action, question)

        try:
            response = await self._openai.chat.completions.create(
                model=settings.vision_model,
                max_tokens=2000 if action in ("read_document", "analyze_schema") else 1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": detail,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            result_text = response.choices[0].message.content or ""
            logger.debug("Vision result", action=action, preview=result_text[:80])

            # ── Stocker dans la mémoire visuelle (fire and forget) ────────────
            asyncio.create_task(
                self._store_memory(result_text, source, action, question),
                name="vision-memory",
            )

            return ToolResult(content=result_text)
        except Exception as e:
            logger.error("Vision API error", error=str(e))
            return ToolResult(content=f"Erreur GPT-4o Vision : {e}", is_error=True)

    def _build_prompt(self, action: str, question: str) -> str:
        if action == "read_document":
            return (
                "Lis et transcris intégralement le texte visible sur ce document. "
                "Conserve la structure (titres, paragraphes, tableaux, listes). "
                "Si c'est une note manuscrite, transcris telle quelle. "
                "Réponds uniquement avec le contenu extrait, sans commentaires."
            )
        if action == "analyze_schema":
            return (
                f"Tu es un expert en électronique, PCB design et schémas techniques. "
                f"Identifie les composants, connexions et problèmes potentiels. "
                f"Sois précis sur les références si lisibles. "
                f"{question or 'Analyse ce schéma/PCB.'}"
            )
        return question

    async def _store_memory(self, description: str, source: str, action: str, context: str) -> None:
        try:
            await self._visual_memory.store(description=description, source=source, context=context)
        except Exception as e:
            logger.debug("Visual memory store failed", error=str(e))

    # ── Captures ──────────────────────────────────────────────────────────────

    def _capture_webcam(self) -> bytes | None:
        """Ouvre la webcam, chauffe 3 frames, capture, ferme. Zéro fichier disque."""
        try:
            import cv2  # type: ignore[import-untyped]
        except ImportError as e:
            logger.error(
                "Vision: dépendance manquante", error=str(e), hint="uv add opencv-python pillow"
            )
            return None

        cap = None
        try:
            cap = cv2.VideoCapture(settings.vision_webcam_index)
            if not cap.isOpened():
                logger.error("Webcam inaccessible", index=settings.vision_webcam_index)
                return None

            # 3 frames de chauffe — exposition + balance des blancs se stabilisent
            for _ in range(3):
                cap.read()

            ret, frame = cap.read()
            if not ret or frame is None:
                logger.error("Frame webcam invalide")
                return None

            # BGR (OpenCV) → RGB → PIL → JPEG en RAM, zéro disque
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
            return buf.getvalue()

        except Exception as e:
            logger.error("Webcam capture error", error=str(e))
            return None
        finally:
            if cap is not None:
                cap.release()

    def _capture_screen(self) -> bytes | None:
        """Capture l'écran en RAM. macOS : screencapture stdout. Fallback : PIL.ImageGrab."""
        if platform.system() == "Darwin":
            result = self._capture_screen_macos()
            if result:
                return result
        return self._capture_screen_pil()

    def _capture_screen_macos(self) -> bytes | None:
        """screencapture → fichier temp → lecture → suppression immédiate.

        Le fichier existe < 100ms. Le stdout de screencapture est vide sur macOS Sonoma+
        (bug Apple connu), d'où le passage par un fichier temporaire.
        """
        import os
        import tempfile

        fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="jarvis_screen_")
        os.close(fd)
        try:
            proc = subprocess.run(
                ["screencapture", "-x", "-t", "jpg", tmp_path],
                capture_output=True,
                timeout=10,
            )
            if proc.returncode != 0:
                logger.debug("screencapture échoué", returncode=proc.returncode)
                return None
            with open(tmp_path, "rb") as f:
                data = f.read()
            if not data:
                logger.debug("screencapture: fichier vide")
                return None
            logger.debug("Screen capture via screencapture", kb=round(len(data) / 1024, 1))
            return self._resize_jpeg(data)
        except Exception as e:
            logger.debug("screencapture tempfile failed", error=str(e))
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _capture_screen_pil(self) -> bytes | None:
        """PIL.ImageGrab — fallback cross-platform."""
        try:
            screenshot = ImageGrab.grab()
            max_w = settings.vision_screen_max_width
            if screenshot.width > max_w:
                ratio = max_w / screenshot.width
                screenshot = screenshot.resize(
                    (max_w, int(screenshot.height * ratio)),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            screenshot.save(buf, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
            logger.debug(
                "Screen capture PIL",
                size=f"{screenshot.width}x{screenshot.height}",
                kb=round(buf.tell() / 1024, 1),
            )
            return buf.getvalue()
        except Exception as e:
            logger.error("Screen capture PIL error", error=str(e))
            return None

    def _resize_jpeg(self, jpeg_bytes: bytes) -> bytes:
        """Redimensionne un JPEG si l'écran dépasse vision_screen_max_width."""
        try:
            img = Image.open(io.BytesIO(jpeg_bytes))
            max_w = settings.vision_screen_max_width
            if img.width <= max_w:
                return jpeg_bytes
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
            logger.debug("Screen resized", width=max_w, kb=round(buf.tell() / 1024, 1))
            return buf.getvalue()
        except Exception:
            return jpeg_bytes
