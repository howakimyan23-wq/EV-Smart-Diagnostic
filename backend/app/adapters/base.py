from abc import ABC, abstractmethod
from dataclasses import dataclass
@dataclass
class Capability:
    supported: bool
    verified: bool   # True only after testing on real hardware
    reason: str
FUNCS = ["read_vin", "read_dtc", "list_ecus", "live_data", "bms", "charging", "freeze_frame"]
class DiagnosticAdapter(ABC):
    name = "base"; simulated = False
    @abstractmethod
    def capabilities(self) -> dict[str, Capability]: ...
    def read_dtc(self): raise NotImplementedError
    def live_data(self): raise NotImplementedError
class NotImplementedAdapter(DiagnosticAdapter):
    """Honest placeholder: every function reports unsupported until real code + hardware tests exist."""
    def __init__(self, name, reason): self.name, self._r = name, reason
    def capabilities(self):
        return {f: Capability(False, False, self._r) for f in FUNCS}
