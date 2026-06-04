"""Show-mode duration and rendering constants.

Pulled out of `pet_controller.py` so the Show subsystem owns its own
tunables. These values were previously module-level constants on the
controller; they only matter during a Show sequence and have no other
callers.
"""

from __future__ import annotations


# Render scale applied to the pet sprite during Show. The sprite grows
# to (width * X, height * Y) so the viewer perceives a "performance"
# even though the actual physics box stays the same.
SHOW_RENDER_SCALE_X: float = 4.6
SHOW_RENDER_SCALE_Y: float = 3.8

# Hover durations (seconds) the Show sequence holds at the apex of
# flight. SHOW_HOVER_SECONDS is the brief hover before the title fades
# in; SHOW_TITLE_SECONDS extends the hover while the title overlay is
# visible.
SHOW_HOVER_SECONDS: float = 0.5
SHOW_TITLE_SECONDS: float = 3.2
