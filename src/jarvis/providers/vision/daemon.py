"""
Daemon vision — détection d'objets YOLOv8n en background.

Tourne en parallèle de FastAPI via asyncio.
Capture les frames webcam à ~2fps et analyse avec YOLOv8n.
Envoie les événements au Gateway via webhook interne ET publie
les bounding boxes normalisées dans VisionObjectsQueue pour
l'affichage temps réel dans le browser.

Note : la détection de gestes et de visage est gérée côté browser
       (mediapipe_vision.js). Ce daemon ne fait que la détection d'objets.
"""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

from jarvis.kernel.permissions import permissions as _perm_store
from jarvis.kernel.settings import settings
from jarvis.providers.vision.face_recognizer import FaceRecognizer
from jarvis.providers.vision.object_detector import ObjectDetector
from jarvis.providers.vision.objects_queue import get_vision_objects_queue

_face_recognizer: FaceRecognizer | None = None


def get_face_recognizer() -> FaceRecognizer | None:
    """Retourne l'instance FaceRecognizer active (ou None si désactivé)."""
    return _face_recognizer


_JARVIS_WEBHOOK = "http://localhost:8000/api/webhooks"
_TARGET_FPS = 2
_FRAME_INTERVAL = 1.0 / _TARGET_FPS


async def run_vision_daemon() -> None:
    """Boucle principale du daemon vision.

    La caméra hardware n'est ouverte que lorsque la permission 'camera' est
    activée depuis l'UI (bouton Caméra). Elle est relachée dès que la
    permission est révoquée, éteignant ainsi le voyant de la webcam.
    """
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        logger.error("Vision daemon: opencv-python non installé — daemon désactivé")
        return

    detector = ObjectDetector(confidence=settings.vision_yolo_confidence)
    objects_q = get_vision_objects_queue()

    global _face_recognizer
    face_recognizer: FaceRecognizer | None = None
    _last_recognition_state: bool = False
    if settings.face_recognition_enabled:
        face_recognizer = FaceRecognizer()
        _face_recognizer = face_recognizer
        logger.info("FaceRecognizer activé dans le daemon vision")

    cap: object | None = None  # ouvert dynamiquement selon la permission
    logger.info("Vision daemon démarré — en attente d'activation caméra")

    loop = asyncio.get_running_loop()

    async with httpx.AsyncClient(timeout=1.0) as client:
        while True:
            loop_start = loop.time()

            # ── Gestion permission caméra ─────────────────────────────────────
            cam_allowed = _perm_store.get("camera")

            if not cam_allowed:
                if cap is not None:
                    await loop.run_in_executor(None, cap.release)
                    cap = None
                    logger.info("Vision daemon: caméra relâchée (permission désactivée)")
                await asyncio.sleep(1.0)
                continue

            # Ouvre la caméra si nécessaire
            if cap is None:
                cap = cv2.VideoCapture(settings.vision_webcam_index)
                if not cap.isOpened():
                    logger.error(
                        "Vision daemon: webcam introuvable", index=settings.vision_webcam_index
                    )
                    cap = None
                    await asyncio.sleep(2.0)
                    continue
                cap.set(cv2.CAP_PROP_FPS, _TARGET_FPS)
                logger.info("Vision daemon: caméra ouverte", fps=_TARGET_FPS)

            # ── Capture + analyse ─────────────────────────────────────────────
            ret, frame = await loop.run_in_executor(None, cap.read)
            if not ret or frame is None:
                await asyncio.sleep(0.5)
                continue

            import cv2 as _cv2

            frame = _cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            result = await loop.run_in_executor(None, detector.process, frame)

            if result:
                boxes = [
                    {
                        "label": o.label,
                        "conf": round(o.confidence, 2),
                        "bbox": [
                            o.bbox[0] / w,
                            o.bbox[1] / h,
                            o.bbox[2] / w,
                            o.bbox[3] / h,
                        ],
                    }
                    for o in result.objects
                ]
                objects_q.publish(boxes)

                if result.new_objects:
                    await _send_event(
                        client,
                        "object_detected",
                        {
                            "new_objects": result.new_objects,
                            "all_objects": [o.label for o in result.objects],
                        },
                    )

            # ── Face recognition ─────────────────────────────────────────────
            if face_recognizer is not None:
                rec = await loop.run_in_executor(None, face_recognizer.process, frame)

                if rec.recognized != _last_recognition_state:
                    _last_recognition_state = rec.recognized
                    await _send_event(
                        client,
                        "face_recognition",
                        {
                            "recognized": rec.recognized,
                            "name": rec.name,
                            "confidence": round(rec.confidence, 2),
                        },
                    )

                if rec.face_locations:
                    color_bgr = (153, 211, 54) if rec.recognized else (68, 68, 239)
                    label = f"{rec.name} {rec.confidence:.0%}"
                    import cv2 as _cv2_face

                    for top, right, bottom, left in rec.face_locations:
                        _cv2_face.rectangle(
                            frame,
                            (left * 4, top * 4),
                            (right * 4, bottom * 4),
                            color_bgr,
                            2,
                        )
                        _cv2_face.putText(
                            frame,
                            label,
                            (left * 4, top * 4 - 8),
                            _cv2_face.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color_bgr,
                            1,
                        )

            elapsed = loop.time() - loop_start
            await asyncio.sleep(max(0.0, _FRAME_INTERVAL - elapsed))

    if cap is not None:
        cap.release()


async def _send_event(client: httpx.AsyncClient, event_type: str, data: dict) -> None:
    try:
        await client.post(f"{_JARVIS_WEBHOOK}/{event_type}", json=data)
    except Exception as e:
        logger.debug("Vision event send failed", error=str(e))
