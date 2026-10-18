# EV Smart Diagnostic

Read-only diagnostic starter for EV, PHEV, and hybrid development. The supplied ZIP contained a static Armenian/English demo and a small FastAPI backend. This update keeps that structure and adds a Linux SocketCAN transport, a restricted generic SAE J1979 reader, API/UI connection, simulation support, and safer deployment defaults.

## Verified Scope

| Function | Current status |
| --- | --- |
| VIN format validation | Implemented for the 17-character VIN shape; the North-American check digit is reported separately and is not used to reject other markets. |
| VIN read | Generic OBD-II Mode 09 PID 02; only when the vehicle responds. Not tested on a physical vehicle. |
| ECU discovery | Limited to ECUs replying to functional OBD-II PID support query; this is not a full ECU/network scan. |
| DTCs | Generic stored Mode 03 and pending Mode 07; only generic descriptions for P0A80, P0AA6, and P0A94 are included. Other codes are returned without an invented description. |
| Live data | Generic PIDs 05, 0C, 0D, and 42 where the ECU advertises them. |
| Freeze frame | Generic Mode 02 request; availability is vehicle-dependent. |
| PHEV BMS, cell voltage/temperature, SOH, charger, inverter, thermal data | Not implemented. Requires authorized vehicle-specific definitions/access. |
| Deepal S06 2025 PHEV | Unverified. No vehicle, VCI, market-specific service data, or authorized diagnostic session was supplied. |
| Coding, clearing DTCs, flashing, immobilizer/security access | Not implemented. The transmit layer blocks these operations. |

All collected records include timestamp and a `simulated` flag. The report marks direct responses as `source: vehicle`, but `verified_on_vehicle` remains false until separately tested on the intended vehicle. A virtual CAN session is restricted to a Linux `vcan*` interface and remains marked as simulated.

## Architecture

- `frontend.html`: existing responsive Armenian/English UI, demo mode, login, vehicle save, VCI status/connect, and real OBD result display.
- `backend/app`: FastAPI, SQLAlchemy persistence, JWT authentication, VIN lookup, SocketCAN/PCAN transport, and SAE J1979/ISO-TP reader.
- `backend/scripts/obd_simulator.py`: read-only test ECU for Linux `vcan0`.
- `backend/tests`: API, VIN, transport allow-list, ISO-TP, DTC, and simulation-provenance tests.

The frontend is served from the same FastAPI origin at `/`. The backend is Python 3.12+ and uses SQLite by default; Docker Compose runs PostgreSQL.

## VCI Comparison

Prices and stock below are from vendor pages checked on 2026-10-17; taxes, cables, shipping, and regional stock can change.

| Device | Connectivity/protocols | API and Linux | Cost/licensing caveat | Assessment |
| --- | --- | --- | --- | --- |
| **PEAK PCAN-USB FD** | Wired USB; one CAN/CAN-FD channel; no wireless or DoIP. | PEAK lists Linux support and PCAN-Basic with Python examples. On Linux, `python-can` documents the PCAN kernel driver through SocketCAN. | Vendor list price €278 before VAT; official page currently lists the USB-C version out of stock. OBD cable is separate; total cable/shipping cost was not published on the checked page. | Recommended Linux-first integration target, subject to stock and correct vehicle connector/bus access. The code uses SocketCAN (`can0`), not a proprietary J2534 stack. |
| **Intrepid ValueCAN 4-2A** | Wired USB; two CAN/CAN-FD channels; no Ethernet/DoIP on this model. | Intrepid lists Linux, Python examples, J2534 and RP1210. `python_ics` is MIT; `libicsneo` is BSD-3-Clause with an extra clause. | Official store hides hardware price; the product page says one Vehicle Spy license is required per adapter. Confirm whether an independent API-only deployment needs that license and get a written quote. | Strong alternative if two channels and Intrepid tooling matter; cannot confirm a total price within budget without a quote. |
| **OBDLink MX+** | Bluetooth; iOS/Android/Windows apps; legislated OBD-II plus stated Ford/GM networks. No CAN-FD, DoIP, J2534, or D-PDU API claim. | Vendor publishes STN/AT command programming references and third-party app support; no official Linux SDK was verified. | $139.95 on the vendor page; this is not a full-system diagnostic license. | Wireless option for generic OBD-II experiments, not the primary Linux/S06 VCI recommendation. |

No candidate above is verified against the 2025 Deepal S06 PHEV. A VCI transports frames; it does not provide the vehicle's private ECU address map, DID/PID definitions, gateway authorization, or manufacturer service data. DoIP/D-PDU support for this target remains unverified. Do not buy an adapter on the assumption it exposes BMS cell data.

## Linux Setup

### Local Development

```bash
cd backend
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
export JWT_SECRET="$(openssl rand -hex 32)"
export BOOTSTRAP_ADMIN_TOKEN="$(openssl rand -hex 32)"
export DATABASE_URL="sqlite:///./dev.db"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the UI or `/docs` for API documentation. Create the first administrator once:

```bash
curl -X POST http://127.0.0.1:8000/auth/bootstrap \
  -H "X-Bootstrap-Token: $BOOTSTRAP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"use-a-long-unique-password"}'
```

The bootstrap endpoint stops working once an admin exists. Public registration creates viewer accounts only. Only admin/technician roles can save vehicles or connect/read from a VCI.

### Docker Compose

```bash
cp backend/.env.example backend/.env
# Replace all three secrets in backend/.env with independent random values.
cd backend
docker compose up --build
```

Docker is optional; it was not available in the inspection environment, so the Compose stack was not executed here. The API container uses Linux host networking for SocketCAN visibility. It binds to `127.0.0.1` by default. To use a phone/tablet on the same trusted LAN, set `API_BIND=0.0.0.0` in `backend/.env`, apply a host firewall rule, and visit `http://<laptop-lan-ip>:8000/`. Do not expose this development API directly to the public internet.

### PCAN-USB FD

1. Install PEAK's Linux driver or use the Linux kernel PCAN USB driver. The `python-can` PCAN documentation describes the kernel `peak_usb` path.
2. Connect the VCI to the laptop and verify the interface with `ip -details link show can0`.
3. Confirm the vehicle connector pinout, bus type, and bitrate from authorized service information before connecting. The OBD cable is a separate item. Do not probe unknown pins or add bus termination to a vehicle network.
4. Configure the host CAN interface using the verified nominal bitrate. For example, only if the target network is confirmed as classic CAN at 500 kbit/s:

```bash
sudo modprobe peak_usb
sudo ip link set can0 up type can bitrate 500000
```

CAN-FD data bitrate and timing are vehicle/network-specific; do not copy a guessed value. The application defaults to classic CAN frames for generic OBD-II.
5. Start the API with `VCI_CHANNEL=can0` and `VCI_SIMULATED=0`, sign in as an admin/technician, select/save the vehicle, then use Connection → Check VCI → Connect → Read OBD-II data.

For a phone/tablet, the VCI remains wired to the Linux laptop. The device opens the laptop-hosted responsive UI over the trusted local network; Bluetooth to the VCI is not part of this implementation.

## Simulated Test First

On Linux, create a virtual CAN interface:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 up
```

Run the simulator in one terminal:

```bash
cd backend
source .venv/bin/activate
python scripts/obd_simulator.py --channel vcan0
```

Run the API in another terminal with `VCI_CHANNEL=vcan0` and `VCI_SIMULATED=1`. The application refuses simulated mode on a non-`vcan*` channel. Sign in, save a test vehicle, connect, and read. Expected simulated responses include VIN `LSVAB4C49SN123456`, generic DTC `P0A80`, and a few standard PIDs. They must remain marked simulated in the screen and database. Remove the virtual interface after testing with `sudo ip link del vcan0`.

Automated tests use fake CAN frames and do not require root, a VCI, or a vehicle:

```bash
cd backend
DEV=1 JWT_SECRET="test-secret-with-at-least-32-characters" \
DATABASE_URL="sqlite:////tmp/ev-smart-diagnostic-tests.db" \
BOOTSTRAP_ADMIN_TOKEN="test-bootstrap-token-that-is-long-enough" \
uv run --python 3.12 --with-requirements requirements.txt pytest -q
```

## Deepal S06 Test Plan

1. Confirm country/market, exact model designation, VIN origin/WMI, and whether the vehicle's diagnostic connector exposes standard OBD-II CAN. The S06/S07 names and powertrain options vary by market; the provided project contains no vehicle-specific data.
2. Obtain authorized Deepal/Changan service information or written confirmation from an authorized distributor for the exact 2025 PHEV variant: connector pinout, bus/protocol, nominal/data bitrates, gateway requirements, supported generic OBD services, and third-party diagnostic terms.
3. Test only the read-only generic OBD-II query set first. Record which ECU responds, VIN source, Mode 03/07 codes, supported PIDs, and Mode 02 availability. Compare outputs with a licensed OEM diagnostic tool.
4. Keep BMS, cell voltage/temperature, SOC/SOH, inverter, charging, thermal, and hybrid ECU data marked unavailable until exact authorized definitions and real-vehicle results exist. Do not guess CAN IDs or UDS DIDs.
5. Add a separate Deepal vehicle profile only after the above is documented and tested. Any security access, coding, erase, actuator, or flashing path remains out of scope without explicit authorization and a reviewed implementation.

## Known Limitations

- No physical PCAN hardware or Deepal vehicle was present; no real-vehicle function is verified.
- Generic OBD-II responses may be absent or limited on a Chinese-market PHEV. Functional OBD ECU replies are not a complete ECU inventory.
- BMS and manufacturer-specific diagnostics are unavailable; DTC descriptions are intentionally sparse and generic.
- Freeze-frame read is exposed through the API but not yet a dedicated UI control.
- SQLite tables use `create_all`; a production schema migration system (Alembic), rate limiting, email verification, and long-term data-retention controls remain future work.
- The database stores VINs in plaintext; restrict filesystem/database access and use a protected deployment/network.
- No native mobile wrapper/PWA is included. The responsive web UI can be used from a phone through the laptop gateway; a native wrapper can follow after field validation.

## Primary References

- [PEAK PCAN-USB FD product and price](https://www.peak-system.com/PCAN-USB-FD.365.0.html)
- [PEAK PCAN-Basic API](https://www.peak-system.com/PCAN-Basic.239.0.html)
- [python-can PCAN Basic interface](https://python-can.readthedocs.io/en/stable/interfaces/pcan.html)
- [python-can SocketCAN and PCAN Linux driver notes](https://python-can.readthedocs.io/en/stable/interfaces/socketcan.html)
- [Intrepid ValueCAN 4-2A specifications](https://intrepidcs.com/products/vehicle-network-adapters/valuecan-4/valuecan-4-2-specifications/)
- [Intrepid ValueCAN 4-2A store listing](https://store.intrepidcs.com/product/VCAN4-2A)
- [Intrepid libicsneo SDK and hardware support](https://github.com/intrepidcs/libicsneo)
- [Intrepid Python API](https://github.com/intrepidcs/python_ics)
- [OBDLink MX+ product](https://www.obdlink.com/products/obdlink-mxp/)
- [OBDLink developer references](https://www.obdlink.com/developers/)