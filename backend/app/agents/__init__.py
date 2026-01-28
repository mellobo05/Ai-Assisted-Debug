"""
Minimal agent/workflow utilities.

This is intentionally lightweight: a YAML workflow defines sequential steps that call registered tools.
"""

from .workflow_runner import run_workflow  # noqa: F401
from .swarm import run_syscros_swarm, SwarmConfig  # noqa: F401

