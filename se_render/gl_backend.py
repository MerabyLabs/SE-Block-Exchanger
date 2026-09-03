"""Create a standalone ModernGL context. Failures stay local so the 2D map can run."""

from __future__ import annotations

from typing import Optional


_CONTEXT_OK: Optional[bool] = None
_LAST_ERROR = ""


def last_gl_error() -> str:
    return _LAST_ERROR


def gl_is_available() -> bool:
    global _CONTEXT_OK
    if _CONTEXT_OK is not None:
        return _CONTEXT_OK
    ctx = try_create_context()
    if ctx is None:
        _CONTEXT_OK = False
        return False
    try:
        ctx.release()
    except Exception:
        pass
    _CONTEXT_OK = True
    return True


def try_create_context():
    """Return a standalone ModernGL context or None."""
    global _LAST_ERROR
    try:
        import moderngl
    except Exception as exc:
        _LAST_ERROR = f"ModernGL is not available: {exc}"
        return None
    try:
        ctx = moderngl.create_standalone_context(require=330)
        return ctx
    except Exception as exc:
        _LAST_ERROR = str(exc) or "Could not create an OpenGL 3.3 context."
        return None


def mark_gl_failed(message: str) -> None:
    global _CONTEXT_OK, _LAST_ERROR
    _CONTEXT_OK = False
    _LAST_ERROR = message


def reset_gl_probe() -> None:
    global _CONTEXT_OK, _LAST_ERROR
    _CONTEXT_OK = None
    _LAST_ERROR = ""
