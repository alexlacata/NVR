"""Shared validation helpers used by more than one model domain."""
from __future__ import annotations

import re

# Slug-style identifier shared by cameras and remote systems ("Mes
# systemes") - both are user-facing, human-picked IDs with the same
# shape, so one pattern serves both rather than duplicating it.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")
