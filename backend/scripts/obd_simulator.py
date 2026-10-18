import argparse
import time

import can


VIN = b"LSVAB4C49SN123456"
RESPONDER_ID = 0x7E8


def response_payload(request: bytes) -> bytes | None:
    if not request:
        return None
    service = request[0]
    pid = request[1] if len(request) > 1 else None
    if service == 0x01 and pid == 0x00:
        return bytes((0x41, 0x00, 0x08, 0x18, 0x00, 0x00))
    if service == 0x01 and pid == 0x05:
        return bytes((0x41, 0x05, 80))
    if service == 0x01 and pid == 0x0C:
        return bytes((0x41, 0x0C, 0x1F, 0x40))
    if service == 0x01 and pid == 0x0D:
        return bytes((0x41, 0x0D, 60))
    if service == 0x03:
        return bytes((0x43, 0x0A, 0x80))
    if service == 0x07:
        return bytes((0x47,))
    if service == 0x09 and pid == 0x02:
        return bytes((0x49, 0x02, 0x01)) + VIN
    if service == 0x02 and pid == 0x00:
        return bytes((0x42, 0x00, 0x00, 80))
    return bytes((0x7F, service, 0x11))


def send_payload(bus: can.BusABC, request_id: int, payload: bytes) -> None:
    if len(payload) <= 7:
        data = bytes((len(payload),)) + payload
        bus.send(can.Message(arbitration_id=RESPONDER_ID, data=data.ljust(8, b"\x00"), is_extended_id=False))
        return

    first = bytes((0x10 | ((len(payload) >> 8) & 0x0F), len(payload) & 0xFF)) + payload[:6]
    bus.send(can.Message(arbitration_id=RESPONDER_ID, data=first, is_extended_id=False))
    flow_control_id = RESPONDER_ID - 8
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        message = bus.recv(max(0.0, deadline - time.monotonic()))
        if message and message.arbitration_id == flow_control_id and message.data[:3] == bytes((0x30, 0, 0)):
            break
    else:
        return

    sequence = 1
    offset = 6
    while offset < len(payload):
        chunk = payload[offset:offset + 7]
        data = bytes((0x20 | sequence,)) + chunk
        bus.send(can.Message(arbitration_id=RESPONDER_ID, data=data.ljust(8, b"\x00"), is_extended_id=False))
        offset += len(chunk)
        sequence = (sequence + 1) & 0x0F
        time.sleep(0.005)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only SAE J1979 responder for a Linux vcan test bus")
    parser.add_argument("--channel", default="vcan0")
    args = parser.parse_args()
    if not args.channel.startswith("vcan"):
        parser.error("The simulator only operates on a vcan* interface")

    with can.Bus(interface="socketcan", channel=args.channel) as bus:
        print(f"Simulated OBD-II ECU listening on {args.channel}; no physical vehicle data")
        while True:
            message = bus.recv()
            if not message or message.is_extended_id or message.arbitration_id != 0x7DF or not message.data:
                continue
            length = message.data[0] & 0x0F
            request = bytes(message.data[1:1 + length])
            payload = response_payload(request)
            if payload:
                send_payload(bus, message.arbitration_id, payload)


if __name__ == "__main__":
    main()