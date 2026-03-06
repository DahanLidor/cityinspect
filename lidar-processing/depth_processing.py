"""LiDAR depth map processing for infrastructure hazard geometry computation.

Processes raw depth maps from iOS ARKit LiDAR scanners to compute:
  - Depth (maximum depression below reference plane)
  - Width and Length (bounding box of damage region)
  - Surface damage area
  - Estimated volume of the defect

Input: raw depth map as numpy array or binary buffer from ARKit depthDataMap.
Output: dictionary of computed measurements in metres.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)

# ARKit LiDAR sensor parameters (iPhone 14 Pro / iPad Pro)
DEFAULT_DEPTH_WIDTH = 256
DEFAULT_DEPTH_HEIGHT = 192
DEFAULT_PIXEL_SIZE_M = 0.005  # approximate ground-plane pixel spacing at 1m distance


@dataclass
class LidarMeasurement:
    depth_m: float
    width_m: float
    length_m: float
    surface_area_m2: float
    volume_m3: float
    damage_mask_ratio: float
    reference_plane_m: float


class DepthProcessor:
    """Processes ARKit LiDAR depth maps to extract hazard geometry."""

    def __init__(
        self,
        depth_threshold_m: float = 0.02,
        min_damage_pixels: int = 50,
        gaussian_sigma: float = 1.5,
    ):
        self.depth_threshold = depth_threshold_m
        self.min_damage_pixels = min_damage_pixels
        self.gaussian_sigma = gaussian_sigma

    def process(self, depth_data: np.ndarray, pixel_size_m: float = DEFAULT_PIXEL_SIZE_M) -> Optional[LidarMeasurement]:
        """
        Process a depth map array and return hazard measurements.

        Args:
            depth_data: 2D numpy array of depth values in metres (H x W).
            pixel_size_m: approximate real-world size of one pixel at ground level.

        Returns:
            LidarMeasurement or None if no significant damage detected.
        """
        if depth_data is None or depth_data.size == 0:
            logger.warning("Empty depth data received")
            return None

        depth = self._preprocess(depth_data)

        # Estimate reference plane (road surface) using robust median
        reference_plane = self._estimate_reference_plane(depth)

        # Compute depression map (positive values = below surface)
        depression = reference_plane - depth
        depression = np.clip(depression, 0, None)

        # Threshold to find damage region
        damage_mask = depression > self.depth_threshold

        # Morphological cleanup
        damage_mask = ndimage.binary_opening(damage_mask, iterations=2)
        damage_mask = ndimage.binary_closing(damage_mask, iterations=2)

        # Find largest connected component
        labeled, num_features = ndimage.label(damage_mask)
        if num_features == 0:
            logger.info("No damage regions detected above threshold")
            return None

        component_sizes = ndimage.sum(damage_mask, labeled, range(1, num_features + 1))
        largest_idx = np.argmax(component_sizes) + 1
        largest_mask = labeled == largest_idx

        num_pixels = int(np.sum(largest_mask))
        if num_pixels < self.min_damage_pixels:
            logger.info(f"Damage region too small: {num_pixels} pixels")
            return None

        # Extract measurements from the largest damage region
        return self._compute_measurements(depth, depression, largest_mask, pixel_size_m, reference_plane)

    def process_from_bytes(
        self,
        raw_bytes: bytes,
        width: int = DEFAULT_DEPTH_WIDTH,
        height: int = DEFAULT_DEPTH_HEIGHT,
        dtype: str = "float32",
    ) -> Optional[LidarMeasurement]:
        """Parse raw binary depth buffer into numpy array and process."""
        try:
            depth_array = np.frombuffer(raw_bytes, dtype=np.dtype(dtype))
            depth_array = depth_array.reshape((height, width))
            return self.process(depth_array)
        except Exception as e:
            logger.error(f"Failed to parse depth buffer: {e}")
            return None

    # ── Private methods ──────────────────────────────────────

    def _preprocess(self, depth: np.ndarray) -> np.ndarray:
        """Clean and smooth the depth map."""
        depth = depth.astype(np.float64)

        # Replace zeros / invalid readings with NaN
        depth[depth <= 0] = np.nan

        # Interpolate NaN gaps
        mask = np.isnan(depth)
        if np.any(mask):
            depth[mask] = np.nanmedian(depth)

        # Gaussian smoothing to reduce sensor noise
        depth = ndimage.gaussian_filter(depth, sigma=self.gaussian_sigma)
        return depth

    @staticmethod
    def _estimate_reference_plane(depth: np.ndarray) -> float:
        """Estimate the flat road surface elevation using robust statistics."""
        # Use the 75th percentile as the reference (most of the surface should be flat)
        return float(np.percentile(depth[~np.isnan(depth)], 75))

    def _compute_measurements(
        self,
        depth: np.ndarray,
        depression: np.ndarray,
        mask: np.ndarray,
        pixel_size: float,
        reference_plane: float,
    ) -> LidarMeasurement:
        """Compute physical measurements from the damage region."""

        # Depth: maximum depression in the region
        region_depression = depression[mask]
        max_depth = float(np.max(region_depression))
        mean_depth = float(np.mean(region_depression))

        # Bounding box → width and length
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        row_min, row_max = np.where(rows)[0][[0, -1]]
        col_min, col_max = np.where(cols)[0][[0, -1]]

        width_m = float((col_max - col_min + 1) * pixel_size)
        length_m = float((row_max - row_min + 1) * pixel_size)

        # Surface area
        num_damage_pixels = int(np.sum(mask))
        surface_area_m2 = float(num_damage_pixels * pixel_size * pixel_size)

        # Volume estimate (sum of depressions × pixel area)
        volume_m3 = float(np.sum(region_depression) * pixel_size * pixel_size)

        # Damage ratio
        total_pixels = mask.size
        damage_ratio = num_damage_pixels / total_pixels

        return LidarMeasurement(
            depth_m=round(max_depth, 4),
            width_m=round(width_m, 4),
            length_m=round(length_m, 4),
            surface_area_m2=round(surface_area_m2, 4),
            volume_m3=round(volume_m3, 6),
            damage_mask_ratio=round(damage_ratio, 4),
            reference_plane_m=round(reference_plane, 4),
        )


def compute_lidar_similarity(measurements_a: dict, measurements_b: dict) -> float:
    """Compute similarity score between two sets of LiDAR measurements (0–1)."""
    keys = ["depth_m", "width_m", "length_m", "surface_area_m2"]
    ratios = []

    for key in keys:
        a = measurements_a.get(key)
        b = measurements_b.get(key)
        if a and b and a > 0 and b > 0:
            ratios.append(min(a, b) / max(a, b))

    return float(np.mean(ratios)) if ratios else 0.0
