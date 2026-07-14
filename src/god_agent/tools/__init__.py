"""Tool interface layer — the agent's hands.

All tools operate through a :class:`~god_agent.workspace.WorkspaceBoundary` and a
:class:`~god_agent.safety.SafetySystem`, so safety is enforced uniformly rather
than relying on each tool to remember the rules.
"""

from .filesystem import FileSystemTool, EditResult, WriteResult
from .shell import ShellTool, ShellResult
from .git_tool import GitTool

__all__ = [
    "FileSystemTool",
    "EditResult",
    "WriteResult",
    "ShellTool",
    "ShellResult",
    "GitTool",
]
