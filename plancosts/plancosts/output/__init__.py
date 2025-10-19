# plancosts/plancosts/output/__init__.py
from .table import to_table  # re-export the function so `plancosts.output.to_table` works

__all__ = ["to_table"]
