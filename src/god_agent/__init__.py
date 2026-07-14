"""GOD Coding Agent.

A safety-first, self-verifying agentic coding system.

Design principles (derived from real-world failure analysis of coding agents):
  1. Deterministic enforcement over wishful instruction — critical rules
     (workspace boundaries, destructive-command blocking) are enforced in code,
     not in prose prompts.
  2. Never trust a "done" claim — every change is independently verified.
  3. Hard workspace boundaries by default — the agent cannot touch paths outside
     the declared project root without an explicit grant.
  4. Reversible by default — backups + checkpoints before any mutation.
"""

__version__ = "0.1.0"

from .workspace import WorkspaceBoundary, BoundaryViolation
from .config import Config

__all__ = ["WorkspaceBoundary", "BoundaryViolation", "Config", "__version__"]
