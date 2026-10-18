import os, hashlib, hmac, secrets, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from .db import get_db
from .models import User
SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    if os.getenv("DEV") == "1": SECRET = "local-development-only-key-not-for-deployment-000000000"
    else: raise RuntimeError("Set JWT_SECRET (or DEV=1 for local testing only)")
if len(SECRET) < 32 and os.getenv("DEV") != "1":
    raise RuntimeError("JWT_SECRET must be at least 32 characters")
def hash_pw(p: str) -> str:
    s = secrets.token_hex(16)
    return s + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), s.encode(), 200_000).hex()
def check_pw(p: str, h: str) -> bool:
    s, d = h.split("$")
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", p.encode(), s.encode(), 200_000).hex(), d)
def make_token(u: User) -> str:
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, SECRET, "HS256")
bearer = HTTPBearer()
def current_user(cred=Depends(bearer), db: Session = Depends(get_db)) -> User:
    try: uid = int(jwt.decode(cred.credentials, SECRET, ["HS256"])["sub"])
    except Exception: raise HTTPException(401, "Invalid token")
    u = db.get(User, uid)
    if not u: raise HTTPException(401, "Unknown user")
    return u
def need(*roles):
    def dep(u: User = Depends(current_user)):
        if u.role not in roles: raise HTTPException(403, "Insufficient role")
        return u
    return dep
