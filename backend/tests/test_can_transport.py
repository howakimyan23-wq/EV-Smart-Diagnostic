import pytest

from app.adapters.can_transport import SocketCanAdapter


class FakeBus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.sent = []
        self.closed = False

    def send(self, message, timeout=None):
        self.sent.append((message, timeout))

    def recv(self, timeout=None):
        return None

    def shutdown(self):
        self.closed = True


def test_socketcan_connection_and_read_only_frame_allow_list():
    buses = []

    def factory(**kwargs):
        bus = FakeBus(**kwargs)
        buses.append(bus)
        return bus

    adapter = SocketCanAdapter(channel="can-test", bus_factory=factory)
    adapter.connect()
    adapter.send_frame(0x7DF, bytes((2, 1, 0x00, 0, 0, 0, 0, 0)))
    assert adapter.status()["connected"] is True
    assert buses[0].kwargs["channel"] == "can-test"
    assert buses[0].sent[0][0].arbitration_id == 0x7DF
    with pytest.raises(ValueError):
        adapter.send_frame(0x7E0, bytes((2, 0x10, 0x01)))
    with pytest.raises(ValueError):
        adapter.send_frame(0x7DF, bytes((1, 0x04, 0, 0, 0, 0, 0, 0)))
    adapter.disconnect()
    assert buses[0].closed is True


def test_simulated_mode_is_limited_to_vcan(monkeypatch):
    monkeypatch.setenv("VCI_SIMULATED", "1")
    adapter = SocketCanAdapter(channel="can0", bus_factory=lambda **kwargs: FakeBus(**kwargs))
    with pytest.raises(ConnectionError):
        adapter.connect()
    virtual_adapter = SocketCanAdapter(channel="vcan0", bus_factory=lambda **kwargs: FakeBus(**kwargs))
    virtual_adapter.connect()
    assert virtual_adapter.status()["simulated"] is True