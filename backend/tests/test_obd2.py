from collections import deque

from app.adapters.can_transport import CanFrame
from app.adapters.obd2 import DiagnosticUnavailable, Obd2Client


class FakeTransport:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.sent = []

    def send_frame(self, arbitration_id, data):
        self.sent.append((arbitration_id, data))

    def receive_frame(self, timeout):
        return self.responses.popleft() if self.responses else None


def test_reads_generic_live_pid_and_labels_provenance():
    transport = FakeTransport([CanFrame(0x7E8, bytes((3, 0x41, 0x0D, 42, 0, 0, 0, 0)))])
    client = Obd2Client(transport, timeout=0.01)
    responses = client.request_all(0x01, 0x0D)
    assert responses[0x7E8] == bytes((0x41, 0x0D, 42))
    assert transport.sent[0][0] == 0x7DF
    assert transport.sent[0][1][:3] == bytes((2, 1, 0x0D))


def test_reassembles_read_only_vin_and_sends_flow_control():
    vin_bytes = b"LSVAB4C49SN123456"
    payload = bytes((0x49, 0x02, 0x01)) + vin_bytes
    first = bytes((0x10, len(payload))) + payload[:6]
    transport = FakeTransport([
        CanFrame(0x7E8, first),
        CanFrame(0x7E8, bytes((0x21,)) + payload[6:13]),
        CanFrame(0x7E8, bytes((0x22,)) + payload[13:20]),
    ])
    client = Obd2Client(transport, timeout=0.02)
    result = client.read_vin()
    assert result["value"] == vin_bytes.decode()
    assert result["source"] == "vehicle"
    assert result["simulated"] is False
    assert transport.sent[1][0] == 0x7E0
    assert transport.sent[1][1][:3] == bytes((0x30, 0, 0))


def test_vin_response_keeps_simulation_provenance():
    vin_bytes = b"LSVAB4C49SN123456"
    payload = bytes((0x49, 0x02, 0x01)) + vin_bytes
    transport = FakeTransport([
        CanFrame(0x7E8, bytes((0x10, len(payload))) + payload[:6]),
        CanFrame(0x7E8, bytes((0x21,)) + payload[6:13]),
        CanFrame(0x7E8, bytes((0x22,)) + payload[13:20]),
    ])
    transport.simulated = True
    result = Obd2Client(transport, timeout=0.01).read_vin()
    assert result["source"] == "simulation"
    assert result["simulated"] is True


def test_rejects_non_read_services():
    client = Obd2Client(FakeTransport([]))
    try:
        client.request_all(0x04)
    except ValueError:
        pass
    else:
        raise AssertionError("Clear-DTC service must not be available")


def test_decodes_dtc_and_bilingual_generic_description():
    assert Obd2Client._decode_dtc(0x0A, 0x80) == "P0A80"
    assert "description_hy" in Obd2Client._dtc_description("P0A80")
    assert "No verified" in Obd2Client._dtc_description("P1234")["description_en"]


def test_live_data_keeps_successful_pids_when_one_is_unavailable():
    class PidTransport(FakeTransport):
        def send_frame(self, arbitration_id, data):
            payload = data[1:1 + data[0]]
            service, pid = payload[0], payload[1] if len(payload) > 1 else None
            if service == 0x01 and pid == 0x00:
                response = bytes((0x41, 0x00, 0x08, 0x18, 0x00, 0x00))
            elif service == 0x01 and pid == 0x05:
                response = bytes((0x7F, 0x01, 0x12))
            elif service == 0x01 and pid == 0x0C:
                response = bytes((0x41, 0x0C, 0x1F, 0x40))
            elif service == 0x01 and pid == 0x0D:
                response = bytes((0x41, 0x0D, 60))
            else:
                return
            self.responses.append(CanFrame(0x7E8, bytes((len(response),)) + response.ljust(7, b"\x00")))

    readings = Obd2Client(PidTransport([]), timeout=0.01).read_live_data()
    assert {reading["name"] for reading in readings} == {"engine_rpm", "vehicle_speed"}