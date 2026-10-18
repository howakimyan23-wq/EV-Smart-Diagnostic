from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from hmac import compare_digest
from .db import Base, engine, get_db
from .models import User, Vehicle, Record, ServiceEntry
from .auth import hash_pw, check_pw, make_token, need
from .vin import vin_valid, vin_check_digit_valid, decode_vin
from .adapters import PCAN, REGISTRY
from .adapters.obd2 import DiagnosticUnavailable, Obd2Client


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="EV Smart Diagnostic API", version="0.3.0", lifespan=lifespan)
class Cred(BaseModel): email: EmailStr; password: str
class VehicleIn(BaseModel): make: str = ""; model: str = ""; year: int | None = None; vin: str | None = None
class RecordIn(BaseModel): kind: str; is_simulated: bool; payload: dict
class NoteIn(BaseModel): note: str
@app.get("/", include_in_schema=False)
def frontend():
    path = Path(os.getenv("FRONTEND_FILE", Path(__file__).resolve().parents[2] / "frontend.html"))
    if not path.is_file(): raise HTTPException(404, "Frontend file is not installed")
    return FileResponse(path)
@app.get("/health")
def health(): return {"ok": True}
@app.post("/auth/register")
def register(c: Cred, db: Session = Depends(get_db)):
    if len(c.password) < 10: raise HTTPException(400, "Password must be at least 10 characters")
    if db.scalar(select(User).where(User.email == c.email)): raise HTTPException(409, "Email already used")
    u = User(email=c.email, password_hash=hash_pw(c.password), role="viewer")
    db.add(u); db.commit(); return {"id": u.id, "role": u.role}
@app.post("/auth/bootstrap")
def bootstrap(c: Cred, x_bootstrap_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    expected = os.getenv("BOOTSTRAP_ADMIN_TOKEN")
    if not expected or len(expected) < 32: raise HTTPException(503, "Admin bootstrap is not configured")
    if not x_bootstrap_token or not compare_digest(x_bootstrap_token, expected): raise HTTPException(403, "Invalid bootstrap token")
    if db.scalar(select(User.id).where(User.role == "admin")): raise HTTPException(409, "Admin already initialized")
    if len(c.password) < 10: raise HTTPException(400, "Password must be at least 10 characters")
    if db.scalar(select(User).where(User.email == c.email)): raise HTTPException(409, "Email already used")
    u = User(email=c.email, password_hash=hash_pw(c.password), role="admin")
    db.add(u); db.commit(); return {"id": u.id, "role": u.role}
@app.post("/auth/login")
def login(c: Cred, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == c.email))
    if not u or not check_pw(c.password, u.password_hash): raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(u), "role": u.role}
@app.get("/vin/{vin}/check")
def vin_check(vin: str, _=Depends(need("admin", "technician", "viewer"))):
    valid_format = vin_valid(vin)
    return {"valid_format": valid_format, "north_american_check_digit_valid": vin_check_digit_valid(vin),
            "check_digit_scope": "Informative only; check-digit requirements vary by market", "identified_on_vehicle": False}
@app.get("/vin/{vin}/decode")
def vin_decode(vin: str, _=Depends(need("admin", "technician", "viewer"))):
    try: return decode_vin(vin)
    except ValueError: raise HTTPException(400, "Invalid VIN")
    except Exception: raise HTTPException(502, "VIN lookup service unavailable")
@app.post("/vehicles")
def add_vehicle(v: VehicleIn, u=Depends(need("admin", "technician")), db: Session = Depends(get_db)):
    vin = v.vin.upper() if v.vin else None
    if vin and not vin_valid(vin): raise HTTPException(400, "Invalid VIN")
    x = Vehicle(owner_id=u.id, make=v.make, model=v.model, year=v.year, vin=vin, vin_source="manual")
    db.add(x); db.commit(); return {"id": x.id, "vin_source": x.vin_source}
@app.get("/vehicles")
def list_vehicles(u=Depends(need("admin", "technician", "viewer")), db: Session = Depends(get_db)):
    q = select(Vehicle) if u.role == "admin" else select(Vehicle).where(Vehicle.owner_id == u.id)
    return [{"id": x.id, "make": x.make, "model": x.model, "year": x.year, "vin": x.vin, "vin_source": x.vin_source} for x in db.scalars(q)]
def own(db, u, vid):
    v = db.get(Vehicle, vid)
    if not v or (u.role != "admin" and v.owner_id != u.id): raise HTTPException(404, "Vehicle not found")
    return v
@app.post("/vehicles/{vid}/records")
def add_record(vid: int, r: RecordIn, u=Depends(need("admin", "technician")), db: Session = Depends(get_db)):
    own(db, u, vid); x = Record(vehicle_id=vid, kind=r.kind, is_simulated=r.is_simulated, payload=r.payload)
    db.add(x); db.commit(); return {"id": x.id, "is_simulated": x.is_simulated}
@app.get("/vehicles/{vid}/records")
def records(vid: int, u=Depends(need("admin", "technician", "viewer")), db: Session = Depends(get_db)):
    own(db, u, vid)
    return [{"id": x.id, "kind": x.kind, "is_simulated": x.is_simulated, "payload": x.payload, "at": x.created_at.isoformat()}
            for x in db.scalars(select(Record).where(Record.vehicle_id == vid).order_by(Record.id.desc()))]
@app.post("/vehicles/{vid}/service")
def add_service(vid: int, n: NoteIn, u=Depends(need("admin", "technician")), db: Session = Depends(get_db)):
    own(db, u, vid); x = ServiceEntry(vehicle_id=vid, note=n.note); db.add(x); db.commit(); return {"id": x.id}
@app.get("/adapters")
def adapters(_=Depends(need("admin", "technician", "viewer"))):
    return {k: {f: vars(c) for f, c in a.capabilities().items()} for k, a in REGISTRY.items()}
@app.get("/vci/status")
def vci_status(_=Depends(need("admin", "technician", "viewer"))):
    return PCAN.status()
@app.post("/vci/connect")
def vci_connect(_=Depends(need("admin", "technician"))):
    try: PCAN.connect()
    except ConnectionError as exc: raise HTTPException(503, str(exc))
    return PCAN.status()
@app.post("/vci/disconnect")
def vci_disconnect(_=Depends(need("admin", "technician"))):
    PCAN.disconnect(); return PCAN.status()
@app.post("/vehicles/{vid}/diagnostics/obd")
def obd_scan(vid: int, u=Depends(need("admin", "technician")), db: Session = Depends(get_db)):
    vehicle = own(db, u, vid)
    if not PCAN.connected: raise HTTPException(503, "Connect a VCI before requesting vehicle diagnostics")
    report = Obd2Client(PCAN).scan()
    report.update({
        "vehicle_id": vid,
        "vehicle_record": {"make": vehicle.make, "model": vehicle.model, "year": vehicle.year},
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    })
    record = Record(vehicle_id=vid, kind="obd_scan", is_simulated=report["simulated"], payload=report)
    db.add(record); db.commit()
    return {"record_id": record.id, **report}
@app.post("/vehicles/{vid}/diagnostics/freeze-frame")
def freeze_frame(
    vid: int,
    pid: int = Query(default=0, ge=0, le=255),
    frame: int = Query(default=0, ge=0, le=255),
    u=Depends(need("admin", "technician")),
    db: Session = Depends(get_db),
):
    own(db, u, vid)
    if not PCAN.connected: raise HTTPException(503, "Connect a VCI before requesting vehicle diagnostics")
    try: result = Obd2Client(PCAN).read_freeze_frame(pid=pid, frame=frame)
    except DiagnosticUnavailable as exc: raise HTTPException(404, str(exc))
    payload = {"source": "simulation" if PCAN.simulated else "vehicle", "simulated": PCAN.simulated,
               "verified_on_vehicle": False, "pid": pid, "frame": frame, "data": result,
               "scanned_at": datetime.now(timezone.utc).isoformat()}
    record = Record(vehicle_id=vid, kind="freeze_frame", is_simulated=payload["simulated"], payload=payload)
    db.add(record); db.commit()
    return {"record_id": record.id, **payload}
