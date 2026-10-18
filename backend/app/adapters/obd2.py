from dataclasses import dataclass
from collections.abc import Callable
import re
import time
from typing import Protocol

from .can_transport import CanFrame


class CanTransport(Protocol):
    def send_frame(self, arbitration_id: int, data: bytes) -> None: ...
    def receive_frame(self, timeout: float) -> CanFrame | None: ...


class DiagnosticUnavailable(Exception):
    pass


@dataclass(frozen=True)
class PidDefinition:
    name: str
    label_en: str
    label_hy: str
    unit: str
    decode: Callable[[bytes], int | float]


class Obd2Client:
    request_id = 0x7DF
    response_ids = range(0x7E8, 0x7F0)
    allowed_services = {0x01, 0x02, 0x03, 0x07, 0x09}

    def __init__(self, transport: CanTransport, timeout: float = 0.8):
        self.transport = transport
        self.timeout = timeout
        self.simulated = bool(getattr(transport, "simulated", False))

    @property
    def source(self) -> str:
        return "simulation" if self.simulated else "vehicle"

    def request_all(self, service: int, pid: int | None = None, extra: bytes = b"") -> dict[int, bytes]:
        if service not in self.allowed_services:
            raise ValueError("Only standard read-only OBD-II services are allowed")
        if pid is not None and not 0 <= pid <= 0xFF:
            raise ValueError("PID must be a byte")
        payload = bytes((service,)) + (bytes((pid,)) if pid is not None else b"") + extra
        if not 1 <= len(payload) <= 6:
            raise ValueError("OBD-II request does not fit a classic CAN single frame")

        frame = bytes((len(payload),)) + payload
        self.transport.send_frame(self.request_id, frame.ljust(8, b"\x00"))
        deadline = time.monotonic() + self.timeout
        responses: dict[int, bytes] = {}
        while time.monotonic() < deadline:
            message = self.transport.receive_frame(max(0.0, deadline - time.monotonic()))
            if message is None:
                break
            if message.is_extended_id or message.arbitration_id not in self.response_ids:
                continue
            response = self._reassemble(message, deadline)
            if response is None or not self._matches(response, service, pid):
                continue
            responses[message.arbitration_id] = response
        return responses

    def _reassemble(self, first: CanFrame, deadline: float) -> bytes | None:
        if not first.data:
            return None
        pci_type = first.data[0] >> 4
        if pci_type == 0:
            length = first.data[0] & 0x0F
            return first.data[1:1 + length] if length <= len(first.data) - 1 else None
        if pci_type != 1 or len(first.data) < 2:
            return None

        total_length = ((first.data[0] & 0x0F) << 8) | first.data[1]
        if total_length <= len(first.data) - 2 or total_length > 4095:
            return None
        response_id = first.arbitration_id
        data = bytearray(first.data[2:])
        self.transport.send_frame(response_id - 8, bytes((0x30, 0, 0, 0, 0, 0, 0, 0)))
        expected_sequence = 1
        while len(data) < total_length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DiagnosticUnavailable("Timed out while receiving a multi-frame OBD-II response")
            follow_up = self.transport.receive_frame(remaining)
            if follow_up is None:
                raise DiagnosticUnavailable("Timed out while receiving a multi-frame OBD-II response")
            if follow_up.arbitration_id != response_id or not follow_up.data:
                continue
            if follow_up.data[0] >> 4 != 2 or follow_up.data[0] & 0x0F != expected_sequence:
                raise DiagnosticUnavailable("Invalid ISO-TP sequence in OBD-II response")
            data.extend(follow_up.data[1:])
            expected_sequence = (expected_sequence + 1) & 0x0F
        return bytes(data[:total_length])

    @staticmethod
    def _matches(response: bytes, service: int, pid: int | None) -> bool:
        if response[:1] == bytes((0x7F,)):
            return len(response) >= 3 and response[1] == service
        return len(response) >= (2 if pid is not None else 1) and response[0] == service + 0x40 and (
            pid is None or response[1] == pid
        )

    @staticmethod
    def _positive(responses: dict[int, bytes], service: int) -> dict[int, bytes]:
        result = {can_id: data for can_id, data in responses.items() if data[0] == service + 0x40}
        if result:
            return result
        if responses:
            nrcs = [data[2] for data in responses.values() if len(data) >= 3 and data[0] == 0x7F]
            if nrcs and all(code in {0x11, 0x12} for code in nrcs):
                raise DiagnosticUnavailable("The vehicle reports this standard OBD-II service as unsupported")
            raise DiagnosticUnavailable("The vehicle did not provide a positive OBD-II response")
        raise DiagnosticUnavailable("No OBD-II response was received")

    def read_vin(self) -> dict:
        responses = self._positive(self.request_all(0x09, 0x02), 0x09)
        for can_id, payload in responses.items():
            if len(payload) < 4 or payload[:3] != bytes((0x49, 0x02, payload[2])):
                continue
            vin = payload[3:20].decode("ascii", errors="ignore").strip(" \x00")
            if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
                return {
                    "value": vin,
                    "source": self.source,
                    "simulated": self.simulated,
                    "verified_on_vehicle": False,
                    "format_valid": True,
                    "note": "Read over generic OBD-II; market-specific VIN check-digit rules were not applied.",
                    "responder_id": f"0x{can_id:X}",
                }
        raise DiagnosticUnavailable("The OBD-II response did not contain a valid 17-character VIN")

    def read_ecus(self) -> list[dict]:
        responses = self._positive(self.request_all(0x01, 0x00), 0x01)
        ecus = []
        for can_id, payload in responses.items():
            if len(payload) < 6:
                continue
            supported = []
            for byte_index, value in enumerate(payload[2:6]):
                for bit_index in range(8):
                    if value & (1 << (7 - bit_index)):
                        supported.append(byte_index * 8 + bit_index + 1)
            ecus.append({"responder_id": f"0x{can_id:X}", "protocol": "SAE J1979 over 11-bit CAN", "supported_pids": supported,
                         "source": self.source, "simulated": self.simulated})
        return ecus

    def read_dtcs(self, service: int = 0x03) -> list[dict]:
        if service not in {0x03, 0x07}:
            raise ValueError("Only stored (03) and pending (07) DTC reads are supported")
        responses = self._positive(self.request_all(service), service)
        dtcs = []
        for can_id, payload in responses.items():
            for offset in range(1, len(payload) - 1, 2):
                first, second = payload[offset], payload[offset + 1]
                if first == 0 and second == 0:
                    continue
                code = self._decode_dtc(first, second)
                dtcs.append({"code": code, **self._dtc_description(code), "responder_id": f"0x{can_id:X}",
                             "source": self.source, "simulated": self.simulated})
        return dtcs

    def read_live_data(self) -> list[dict]:
        supported_ecus = self.read_ecus()
        supported = {pid for ecu in supported_ecus for pid in ecu["supported_pids"]}
        definitions = {
            0x05: PidDefinition("coolant_temperature", "Coolant temperature", "Հովացուցիչ հեղուկի ջերմաստիճան", "°C", lambda b: b[0] - 40),
            0x0C: PidDefinition("engine_rpm", "Engine speed", "Շարժիչի պտույտներ", "rpm", lambda b: (b[0] * 256 + b[1]) / 4),
            0x0D: PidDefinition("vehicle_speed", "Vehicle speed", "Մեքենայի արագություն", "km/h", lambda b: b[0]),
            0x42: PidDefinition("control_module_voltage", "Control module voltage", "Կառավարման մոդուլի լարում", "V", lambda b: (b[0] * 256 + b[1]) / 1000),
        }
        readings = []
        for pid, definition in definitions.items():
            if pid not in supported:
                continue
            try:
                responses = self._positive(self.request_all(0x01, pid), 0x01)
            except DiagnosticUnavailable:
                continue
            for can_id, payload in responses.items():
                data = payload[2:]
                required = 2 if pid in {0x0C, 0x42} else 1
                if len(data) < required:
                    continue
                readings.append({
                    "name": definition.name,
                    "label_en": definition.label_en,
                    "label_hy": definition.label_hy,
                    "value": definition.decode(data),
                    "unit": definition.unit,
                    "source": self.source,
                    "simulated": self.simulated,
                    "responder_id": f"0x{can_id:X}",
                })
        if not readings:
            raise DiagnosticUnavailable("No supported standard live-data PID returned a value")
        return readings

    def read_freeze_frame(self, pid: int = 0x00, frame: int = 0) -> list[dict]:
        if not 0 <= frame <= 0xFF:
            raise ValueError("Freeze-frame index must be a byte")
        responses = self._positive(self.request_all(0x02, pid, bytes((frame,))), 0x02)
        return [
            {"responder_id": f"0x{can_id:X}", "pid": pid, "frame": frame, "raw": payload.hex(),
             "source": self.source, "simulated": self.simulated}
            for can_id, payload in responses.items()
        ]

    def scan(self) -> dict:
        result = {
            "source": self.source,
            "simulated": self.simulated,
            "verified_on_vehicle": False,
            "vehicle": self._attempt(self.read_vin),
            "ecus": self._attempt(self.read_ecus),
            "stored_dtcs": self._attempt(self.read_dtcs),
            "pending_dtcs": self._attempt(lambda: self.read_dtcs(0x07)),
            "live_data": self._attempt(self.read_live_data),
            "freeze_frame": {"status": "not_requested", "reason": "Read separately after reviewing stored DTCs"},
            "bms": {"status": "unavailable", "reason": "No Deepal-specific BMS data definition or access authorization is integrated"},
            "restricted_functions": ["ECU coding", "firmware flashing", "security access", "immobilizer operations", "DTC clearing"],
        }
        return result

    @staticmethod
    def _attempt(operation):
        try:
            return {"status": "available", "data": operation()}
        except DiagnosticUnavailable as exc:
            return {"status": "unavailable", "reason": str(exc)}

    @staticmethod
    def _decode_dtc(first: int, second: int) -> str:
        family = "PCBU"[(first >> 6) & 0x03]
        first_digit = (first >> 4) & 0x03
        return f"{family}{first_digit}{first & 0x0F:X}{second >> 4:X}{second & 0x0F:X}"

    @staticmethod
    def _dtc_description(code: str) -> dict[str, str]:
        descriptions = {
            "P0A80": ("Hybrid/EV battery pack deterioration (generic label)", "Մարտկոցի փաթեթի վատթարացում (ընդհանուր նկարագրություն)"),
            "P0AA6": ("Hybrid/EV high-voltage isolation fault (generic label)", "Բարձր լարման մեկուսացման խափանում (ընդհանուր նկարագրություն)"),
            "P0A94": ("DC/DC converter performance fault (generic label)", "DC/DC փոխարկիչի աշխատանքի խափանում (ընդհանուր նկարագրություն)"),
        }
        en, hy = descriptions.get(code, ("No verified generic description; consult the vehicle service information", "Ստուգված ընդհանուր նկարագրություն չկա․ ստուգեք մեքենայի սպասարկման տվյալները"))
        return {"description_en": en, "description_hy": hy}