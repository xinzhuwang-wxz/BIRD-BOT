"""BirdBot domain tools, registered into the nanobot kernel via entry_points.

Tools here are plain ``nanobot.agent.tools.base.Tool`` subclasses exported through
the ``nanobot.tools`` entry-point group declared in this package's pyproject. The
kernel's ToolLoader discovers and registers them automatically on install — no
edits to the kernel are required.
"""
