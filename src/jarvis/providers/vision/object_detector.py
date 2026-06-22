# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""
Détection d'objets en temps réel avec YOLOv8n.
Deux modes :
- Continu (background) : détecte et notifie si un objet nouveau apparaît
- À la demande : analyse fine d'un objet spécifique via GPT-4o Vision
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger


@dataclass
class DetectedObject:
    label: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) pixels


@dataclass
class DetectionResult:
    objects: list[DetectedObject]
    new_objects: list[str]  # labels apparus depuis la dernière frame
    disappeared: list[str]  # labels disparus depuis la dernière frame


class ObjectDetector:
    """Wrapper YOLOv8n avec tracking des changements.

    Notifie uniquement quand l'état change (objet nouveau ou disparu).
    """

    INTERESTING_CLASSES = {
        "laptop",
        "cell phone",
        "book",
        "scissors",
        "knife",
        "remote",
        "keyboard",
        "mouse",
        "monitor",
        "tv",
        "cup",
        "bottle",
        "bowl",
        "person",
    }

    def __init__(self, confidence: float = 0.5) -> None:
        self._model = None
        self._confidence = confidence
        self._previous_labels: set[str] = set()
        self._last_detection_time = 0.0
        self._DETECTION_INTERVAL = 0.5  # 2x/sec

    def _load_model(self) -> None:
        if self._model is None:
            from ultralytics import YOLO  # type: ignore[import-untyped]

            self._model = YOLO("yolov8n.pt")
            logger.info("YOLOv8n model loaded")

    def process(self, frame_bgr: object) -> DetectionResult | None:
        """Analyse une frame. Retourne None si pas encore le moment."""
        now = time.time()
        if now - self._last_detection_time < self._DETECTION_INTERVAL:
            return None
        self._last_detection_time = now

        self._load_model()

        results = self._model(frame_bgr, verbose=False, conf=self._confidence)

        detected: list[DetectedObject] = []
        current_labels: set[str] = set()

        for box in results[0].boxes:
            label = results[0].names[int(box.cls)]
            conf = float(box.conf)
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detected.append(DetectedObject(label=label, confidence=conf, bbox=(x1, y1, x2, y2)))
            current_labels.add(label)

        new_objects = list((current_labels - self._previous_labels) & self.INTERESTING_CLASSES)
        disappeared = list((self._previous_labels - current_labels) & self.INTERESTING_CLASSES)
        self._previous_labels = current_labels

        return DetectionResult(objects=detected, new_objects=new_objects, disappeared=disappeared)

    def draw_boxes(self, frame: object, result: DetectionResult) -> object:
        """Dessine les bounding boxes sur la frame."""
        import cv2  # type: ignore[import-untyped]

        if not result:
            return frame

        annotated = frame.copy()
        for obj in result.objects:
            x1, y1, x2, y2 = obj.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (74, 158, 255), 1)
            cv2.putText(
                annotated,
                f"{obj.label} {obj.confidence:.0%}",
                (x1, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (74, 158, 255),
                1,
            )
        return annotated
