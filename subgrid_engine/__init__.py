"""
Subgrid Engine package.
Provides multi-grid hierarchy parsing, rotor/hinge/piston tracking, and 2.5D/isometric matrix previews.
"""

from subgrid_engine.hierarchy_parser import (
    SubgridHierarchyParser,
    SubgridNode,
    MultiGridStructure,
    MechanicalLink,
)
from subgrid_engine.visualizer_matrix import (
    GridMatrixVisualizer,
    GridMatrixSummary,
    GridBoundingBox,
    VoxelBlockPoint,
)

__all__ = [
    "SubgridHierarchyParser",
    "SubgridNode",
    "MultiGridStructure",
    "MechanicalLink",
    "GridMatrixVisualizer",
    "GridMatrixSummary",
    "GridBoundingBox",
    "VoxelBlockPoint",
]
