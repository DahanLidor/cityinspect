"""Geometry utilities for LiDAR point cloud and depth map analysis.

Provides functions for:
  - Plane fitting via RANSAC
  - Point cloud to mesh surface area estimation
  - Convex hull volume computation
  - Damage region contour extraction
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.spatial import ConvexHull, Delaunay

logger = logging.getLogger(__name__)


def fit_plane_ransac(
    points: np.ndarray,
    n_iterations: int = 1000,
    distance_threshold: float = 0.01,
) -> tuple[np.ndarray, float]:
    """
    Fit a plane to 3D points using RANSAC.

    Args:
        points: (N, 3) array of [x, y, z] points.
        n_iterations: number of RANSAC iterations.
        distance_threshold: inlier distance threshold in metres.

    Returns:
        (normal_vector, d) where ax + by + cz + d = 0.
    """
    best_inliers = 0
    best_plane = (np.array([0, 0, 1.0]), 0.0)
    n = len(points)

    for _ in range(n_iterations):
        idx = np.random.choice(n, 3, replace=False)
        p1, p2, p3 = points[idx]

        v1 = p2 - p1
        v2 = p3 - p1
        normal = np.cross(v1, v2)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-10:
            continue
        normal /= norm_len
        d = -np.dot(normal, p1)

        distances = np.abs(points @ normal + d)
        inliers = np.sum(distances < distance_threshold)

        if inliers > best_inliers:
            best_inliers = inliers
            best_plane = (normal, d)

    return best_plane


def compute_surface_area_delaunay(points_2d: np.ndarray, z_values: np.ndarray) -> float:
    """
    Estimate surface area of a 3D surface defined by 2D points with Z values
    using Delaunay triangulation.

    Args:
        points_2d: (N, 2) array of [x, y] ground plane coordinates.
        z_values: (N,) array of elevation values.

    Returns:
        Total surface area in square metres.
    """
    if len(points_2d) < 3:
        return 0.0

    try:
        tri = Delaunay(points_2d)
    except Exception:
        return 0.0

    total_area = 0.0
    for simplex in tri.simplices:
        p0 = np.array([points_2d[simplex[0], 0], points_2d[simplex[0], 1], z_values[simplex[0]]])
        p1 = np.array([points_2d[simplex[1], 0], points_2d[simplex[1], 1], z_values[simplex[1]]])
        p2 = np.array([points_2d[simplex[2], 0], points_2d[simplex[2], 1], z_values[simplex[2]]])

        triangle_area = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0))
        total_area += triangle_area

    return float(total_area)


def compute_volume_below_plane(
    points: np.ndarray,
    plane_normal: np.ndarray,
    plane_d: float,
) -> float:
    """
    Estimate the volume below a reference plane using convex hull.

    Args:
        points: (N, 3) array of 3D points in the damage region.
        plane_normal: normal vector of the reference plane.
        plane_d: plane offset.

    Returns:
        Estimated volume in cubic metres.
    """
    # Project points to below the plane
    distances = points @ plane_normal + plane_d
    below_mask = distances < 0
    below_points = points[below_mask]

    if len(below_points) < 4:
        return 0.0

    try:
        hull = ConvexHull(below_points)
        return float(hull.volume)
    except Exception:
        return 0.0


def depth_map_to_point_cloud(
    depth_map: np.ndarray,
    pixel_size_m: float = 0.005,
    origin: Optional[tuple[float, float, float]] = None,
) -> np.ndarray:
    """
    Convert a 2D depth map to a 3D point cloud.

    Args:
        depth_map: (H, W) array of depth values.
        pixel_size_m: ground-plane pixel spacing.
        origin: optional (x, y, z) offset for the point cloud.

    Returns:
        (N, 3) array of [x, y, z] points.
    """
    h, w = depth_map.shape
    origin = origin or (0.0, 0.0, 0.0)

    ys, xs = np.mgrid[0:h, 0:w]
    x_coords = xs.astype(float) * pixel_size_m + origin[0]
    y_coords = ys.astype(float) * pixel_size_m + origin[1]
    z_coords = depth_map + origin[2]

    points = np.stack([x_coords.ravel(), y_coords.ravel(), z_coords.ravel()], axis=1)

    # Filter invalid points
    valid = np.isfinite(points).all(axis=1) & (points[:, 2] > 0)
    return points[valid]
