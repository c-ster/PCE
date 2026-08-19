class SourceRootViolation(Exception):
    """Raised when an adapter is asked to read a path outside its approved
    source roots. See docs/PRIVACY.md "Local file safety"."""
