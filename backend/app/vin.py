
_MAP = {**{c: i for i, c in enumerate("0123456789")},
        **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
        **dict(zip("STUVWXYZ", [2, 3, 4, 5, 6, 7, 8, 9]))}
_W = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
def vin_valid(vin: str) -> bool:
    vin = vin.upper()
    return len(vin) == 17 and all(c in _MAP for c in vin)

def vin_check_digit_valid(vin: str) -> bool:
    vin = vin.upper()
    if not vin_valid(vin): return False
    r = sum(_MAP[c] * w for c, w in zip(vin, _W)) % 11
    return vin[8] == ("X" if r == 10 else str(r))
def decode_vin(vin: str) -> dict:
    """Public NHTSA vPIC lookup. Coverage is incomplete (mainly US-market vehicles).
    The result is a lookup, NOT proof the connected vehicle was identified."""
    if not vin_valid(vin): raise ValueError("invalid VIN")
    import httpx
    r = httpx.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json", timeout=15)
    r.raise_for_status()
    d = {i["Variable"]: i["Value"] for i in r.json()["Results"] if i.get("Value")}
    return {"source": "NHTSA vPIC", "verified_on_vehicle": False,
            "make": d.get("Make"), "model": d.get("Model"), "year": d.get("Model Year"),
            "electrification": d.get("Electrification Level"), "fuel": d.get("Fuel Type - Primary")}
