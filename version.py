"""
Application version metadata.

This is the single source of truth for versioning across CLI, GUI, and packaging.
"""

from datetime import date

__version__ = "3.2.1"
__build_date__ = date.today().isoformat()
__channel__ = "stable"  # stable | beta | dev

