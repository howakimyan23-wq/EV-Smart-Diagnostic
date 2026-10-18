from .base import NotImplementedAdapter
from .can_transport import SocketCanAdapter

PCAN = SocketCanAdapter()
REGISTRY = {
    "pcan_socketcan": PCAN,
    "uds": NotImplementedAdapter("uds", "Not implemented yet (Stage 4)"),
    "manufacturer_sdk": NotImplementedAdapter("manufacturer_sdk", "Needs an authorized SDK; none integrated"),
    "bms": NotImplementedAdapter("bms", "Depends on vehicle and VCI; unverified"),
}
