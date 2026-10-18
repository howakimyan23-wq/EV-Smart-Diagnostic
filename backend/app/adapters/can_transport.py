from dataclasses import dataclass
import os
from typing import Any, Callable

from .base import Capability, FUNCS


@dataclass(frozen=True)
class CanFrame:
    arbitration_id: int
    data: bytes
    is_extended_id: bool = False


class SocketCanAdapter:
    name = "pcan_socketcan"
    simulated = False
    _request_id = 0x7DF

    def __init__(
        self,
        channel: str | None = None,
        can_fd: bool | None = None,
        bus_factory: Callable[..., Any] | None = None,
    ):
        self.channel = channel or os.getenv("VCI_CHANNEL", "can0")
        self.can_fd = can_fd if can_fd is not None else os.getenv("VCI_CAN_FD", "0") == "1"
        self.simulated = os.getenv("VCI_SIMULATED", "0") == "1"
        self._bus_factory = bus_factory
        self._bus: Any | None = None

    @property
    def connected(self) -> bool:
        return self._bus is not None

    def connect(self) -> None:
        if self.connected:
            return
        if self.simulated and not self.channel.startswith("vcan"):
            raise ConnectionError("Simulated VCI mode may only use a Linux vcan interface")
        try:
            import can

            factory = self._bus_factory or can.Bus
            self._bus = factory(
                interface="socketcan",
                channel=self.channel,
                fd=self.can_fd,
                can_filters=[{"can_id": 0x7E8, "can_mask": 0x7F8, "extended": False}],
            )
        except Exception as exc:
            self._bus = None
            raise ConnectionError(
                f"Could not open SocketCAN channel {self.channel}; check the VCI driver, interface, and permissions"
            ) from exc

    def disconnect(self) -> None:
        if self._bus is not None:
            self._bus.shutdown()
            self._bus = None

    def send_frame(self, arbitration_id: int, data: bytes) -> None:
        if self._bus is None:
            raise ConnectionError("VCI is not connected")
        if not data or len(data) > 8:
            raise ValueError("Only classic CAN frames with 1 to 8 data bytes are allowed")
        if arbitration_id == self._request_id:
            service = data[1] if data[0] <= 6 and len(data) > 1 else None
            if service not in {0x01, 0x02, 0x03, 0x07, 0x09}:
                raise ValueError("Only standard read-only OBD-II services are allowed")
        elif 0x7E0 <= arbitration_id <= 0x7E7:
            if data[0] != 0x30 or data[1:3] != bytes((0, 0)) or any(data[3:]):
                raise ValueError("Only zero-padded ISO-TP flow-control frames are allowed")
        else:
            raise ValueError("Transmit ID is outside the read-only OBD-II allow-list")

        import can

        message = can.Message(
            arbitration_id=arbitration_id,
            data=data,
            is_extended_id=False,
            is_fd=False,
        )
        self._bus.send(message, timeout=0.2)

    def receive_frame(self, timeout: float) -> CanFrame | None:
        if self._bus is None:
            raise ConnectionError("VCI is not connected")
        message = self._bus.recv(timeout)
        if message is None:
            return None
        return CanFrame(
            arbitration_id=message.arbitration_id,
            data=bytes(message.data),
            is_extended_id=message.is_extended_id,
        )

    def capabilities(self) -> dict[str, Capability]:
        reason = "Generic 11-bit SAE J1979 software path; vehicle compatibility is not verified"
        capabilities = {name: Capability(False, False, "No generic implementation") for name in FUNCS}
        for name in ("read_vin", "read_dtc", "list_ecus", "live_data", "freeze_frame"):
            capabilities[name] = Capability(True, False, reason)
        capabilities.update({
            "bms": Capability(False, False, "Requires vehicle-specific data and access; not integrated"),
            "charging": Capability(False, False, "Requires vehicle-specific data and access; not integrated"),
            "can_transport": Capability(True, False, "SocketCAN transport configured; hardware not verified"),
        })
        return capabilities

    def status(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "interface": "socketcan",
            "channel": self.channel,
            "can_fd_enabled": self.can_fd,
            "connected": self.connected,
            "simulated": self.simulated,
            "verified_on_vehicle": False,
        }