"""
Subgrid Engine package.
Parses CubeGrid parent/child links and extracts block voxels for the map canvas.
"""

from subgrid_engine.hierarchy_parser import (
    MechanicalLink,
    MultiGridStructure,
    SubgridHierarchyParser,
    SubgridNode,
)
from subgrid_engine.visualizer_matrix import (
    GridBoundingBox,
    GridMatrixSummary,
    GridMatrixVisualizer,
    VoxelBlockPoint,
)
from subgrid_engine.projector_splitter import (
    ProjectorSplitter,
    ProjectorSplitResult,
    SplitBlueprintEntry,
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
    "ProjectorSplitter",
    "ProjectorSplitResult",
    "SplitBlueprintEntry",
]
