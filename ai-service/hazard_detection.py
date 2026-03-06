"""YOLOv8-based hazard detection for municipal infrastructure damage.

This module wraps Ultralytics YOLOv8 to classify road hazards into:
  - pothole
  - broken_sidewalk
  - crack
  - road_damage

In production, replace the placeholder model path with a fine-tuned checkpoint.
For the MVP, this falls back to a general pretrained model with label mapping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Hazard class label mapping (index → label)
HAZARD_CLASSES = {
    0: "pothole",
    1: "broken_sidewalk",
    2: "crack",
    3: "road_damage",
}

# Fallback mapping from COCO/pretrained classes to our hazard types
COCO_FALLBACK_MAP = {
    "pothole": "pothole",
    "hole": "pothole",
    "crack": "crack",
    "damage": "road_damage",
}


@dataclass
class DetectionResult:
    hazard_type: str
    confidence: float
    bounding_box: Optional[list[float]] = None
    model_version: str = "yolov8n-hazard-v1"


class HazardDetector:
    """Loads a YOLOv8 model and runs hazard inference on images."""

    def __init__(self, model_path: str = "/models/yolov8_hazard.pt", confidence_threshold: float = 0.45):
        self.confidence_threshold = confidence_threshold
        self.model_path = model_path
        self.model = None
        self.model_version = "yolov8n-hazard-v1"
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            path = Path(self.model_path)
            if path.exists():
                logger.info(f"Loading custom hazard model from {self.model_path}")
                self.model = YOLO(str(path))
            else:
                logger.warning(f"Custom model not found at {self.model_path}. Loading pretrained YOLOv8n.")
                self.model = YOLO("yolov8n.pt")
                self.model_version = "yolov8n-pretrained-fallback"
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None

    def detect(self, image: Image.Image) -> DetectionResult:
        """Run detection on a PIL Image."""
        if self.model is None:
            return self._fallback_detection(image)

        try:
            results = self.model(image, verbose=False)
            return self._parse_results(results)
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return self._fallback_detection(image)

    def detect_from_bytes(self, image_bytes: bytes) -> DetectionResult:
        """Run detection on raw image bytes."""
        from io import BytesIO
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        return self.detect(image)

    def _parse_results(self, results) -> DetectionResult:
        """Parse YOLO results into a DetectionResult."""
        best_conf = 0.0
        best_class = "road_damage"
        best_box = None

        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for i in range(len(boxes)):
                conf = float(boxes.conf[i])
                cls_id = int(boxes.cls[i])
                box = boxes.xyxy[i].tolist()

                if conf < self.confidence_threshold:
                    continue

                # Map class ID to hazard type
                if cls_id in HAZARD_CLASSES:
                    hazard = HAZARD_CLASSES[cls_id]
                else:
                    # Try to map from model's own class names
                    class_name = self.model.names.get(cls_id, "").lower()
                    hazard = self._map_class_name(class_name)

                if conf > best_conf:
                    best_conf = conf
                    best_class = hazard
                    best_box = box

        if best_conf < self.confidence_threshold:
            return self._fallback_detection(None)

        return DetectionResult(
            hazard_type=best_class,
            confidence=round(best_conf, 4),
            bounding_box=best_box,
            model_version=self.model_version,
        )

    @staticmethod
    def _map_class_name(name: str) -> str:
        for key, hazard in COCO_FALLBACK_MAP.items():
            if key in name:
                return hazard
        return "road_damage"

    @staticmethod
    def _fallback_detection(image: Optional[Image.Image]) -> DetectionResult:
        """Simple heuristic fallback when model is unavailable."""
        logger.warning("Using fallback heuristic detection")

        if image is not None:
            arr = np.array(image)
            # Dark region ratio as a crude pothole indicator
            gray = np.mean(arr, axis=2) if len(arr.shape) == 3 else arr
            dark_ratio = np.mean(gray < 60)

            if dark_ratio > 0.15:
                return DetectionResult(hazard_type="pothole", confidence=0.55)
            elif dark_ratio > 0.05:
                return DetectionResult(hazard_type="crack", confidence=0.45)

        return DetectionResult(hazard_type="road_damage", confidence=0.30)
