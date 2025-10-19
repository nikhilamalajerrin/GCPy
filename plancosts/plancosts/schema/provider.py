from __future__ import annotations
from typing import Protocol, List, Any, runtime_checkable

@runtime_checkable
class Provider(Protocol):
    """
    Python analogue 

        type Provider interface {
            ProcessArgs(*cli.Context) error
            LoadResources() ([]*Resource, error)
        }

    In Python:
    - process_args(args): mutate internal state or validate; raise ValueError on bad args.
    - load_resources(): return a list of typed resources; raise on errors.
    """
    def process_args(self, args: Any) -> None: ...
    def load_resources(self) -> List[Any]: ...
