"""
Application version metadata.

This is the single source of truth for versioning across CLI, GUI, and packaging.
"""

from datetime import date

__version__ = "4.0.0"
__build_date__ = date.today().isoformat()
__channel__ = "candidate"  # Do not publish until release_acceptance.json passes.

