"""Local Space Engineers install access. Never copies Keen assets into the repo."""

from se_assets.install_locator import (
    SPACE_ENGINEERS_APP_ID,
    InstallStatus,
    detect_install,
    normalize_install_root,
    resolve_install,
    validate_install,
)
from se_assets.cube_catalog import BlockDefinition, CubeBlockCatalog

__all__ = [
    "SPACE_ENGINEERS_APP_ID",
    "InstallStatus",
    "detect_install",
    "normalize_install_root",
    "resolve_install",
    "validate_install",
    "BlockDefinition",
    "CubeBlockCatalog",
]
