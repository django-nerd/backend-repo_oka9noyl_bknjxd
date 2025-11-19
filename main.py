import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from math import radians, sin, cos, asin, sqrt

from database import db, create_document, get_documents
from schemas import Team, Matchpost, Message

app = FastAPI(title="FindRivals API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------
# Utilities
# ---------------------------
SPORT_PREFIX = {
    "cricket": "CRK",
    "football": "FTB",
    "kabaddi": "KBD",
    "shuttle": "SHT",
    "tennis": "TNS",
}


def generate_team_id(sport: str) -> str:
    prefix = SPORT_PREFIX.get(sport, "TMP")
    # Use count of existing teams for this sport + random suffix
    try:
        count = db["team"].count_documents({"sport": sport}) if db else 0
    except Exception:
        count = 0
    suffix = 100 + count
    return f"{prefix}-{suffix}"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # distance in km
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


# ---------------------------
# Basic
# ---------------------------
@app.get("/")
def read_root():
    return {"message": "FindRivals API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, "name", "Unknown")
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:60]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:60]}"
    return response


# ---------------------------
# Team Registration
# ---------------------------
class TeamCreate(BaseModel):
    team_name: str
    sport: str
    players: List[str] = []
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_preference: str
    contact_number: str
    availability: List[str] = []


@app.post("/teams", response_model=dict)
def register_team(payload: TeamCreate):
    # Ensure players unique across teams (soft check by name)
    if payload.players:
        existing = db["team"].find_one({"players": {"$in": payload.players}})
        if existing:
            raise HTTPException(status_code=400, detail="One or more players already belong to another team")

    team_id = generate_team_id(payload.sport)
    team = Team(
        team_name=payload.team_name,
        sport=payload.sport,
        players=payload.players or [],
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        contact_preference=payload.contact_preference,
        contact_number=payload.contact_number,
        availability=payload.availability or [],
        team_id=team_id,
    )
    inserted_id = create_document("team", team)
    return {"ok": True, "team_id": team_id, "id": inserted_id}


@app.get("/teams", response_model=list)
def list_teams(sport: Optional[str] = None):
    q = {"sport": sport} if sport else {}
    items = get_documents("team", q)
    # stringify _id for frontend
    for it in items:
        it["id"] = str(it.pop("_id", ""))
    return items


@app.get("/teams/{team_id}", response_model=dict)
def get_team(team_id: str):
    doc = db["team"].find_one({"team_id": team_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Team not found")
    doc["id"] = str(doc.pop("_id", ""))
    return doc


# ---------------------------
# Match Posts & Feed
# ---------------------------
class MatchCreate(BaseModel):
    team_id: str
    sport: str
    num_players: int
    time_pref: str
    note: Optional[str] = None


@app.post("/matchposts", response_model=dict)
def create_match_post(payload: MatchCreate):
    team = db["team"].find_one({"team_id": payload.team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    mp = Matchpost(
        team_id=payload.team_id,
        sport=payload.sport,
        num_players=payload.num_players,
        time_pref=payload.time_pref,
        note=payload.note,
        location_name=team.get("location_name"),
        latitude=team.get("latitude"),
        longitude=team.get("longitude"),
    )
    inserted_id = create_document("matchpost", mp)
    return {"ok": True, "id": inserted_id}


@app.get("/feed", response_model=list)
def match_feed(sport: Optional[str] = None):
    q = {"sport": sport} if sport else {}
    items = get_documents("matchpost", q)
    for it in items:
        it["id"] = str(it.pop("_id", ""))
    # sort by created_at desc if present
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


# ---------------------------
# Nearby Opponents
# ---------------------------
@app.get("/nearby", response_model=list)
def nearby_teams(
    sport: Optional[str] = None,
    center_lat: Optional[float] = Query(None),
    center_lon: Optional[float] = Query(None),
    range_km: float = Query(10, ge=1, le=100),
):
    q = {"sport": sport} if sport else {}
    teams = get_documents("team", q)
    result = []
    for t in teams:
        t["id"] = str(t.pop("_id", ""))
        lat, lon = t.get("latitude"), t.get("longitude")
        if center_lat is None or center_lon is None or lat is None or lon is None:
            # if coordinates not provided, include all
            result.append(t)
        else:
            try:
                dist = haversine(center_lat, center_lon, lat, lon)
                if dist <= range_km:
                    t["distance_km"] = round(dist, 2)
                    result.append(t)
            except Exception:
                result.append(t)
    # if we computed distances, sort by distance
    result.sort(key=lambda x: x.get("distance_km", 0))
    return result


# ---------------------------
# Simple Chat
# ---------------------------
class ChatCreate(BaseModel):
    from_team_id: str
    to_team_id: str
    text: str


@app.post("/chat", response_model=dict)
def send_message(payload: ChatCreate):
    # Ensure both teams exist
    a = db["team"].find_one({"team_id": payload.from_team_id})
    b = db["team"].find_one({"team_id": payload.to_team_id})
    if not a or not b:
        raise HTTPException(status_code=404, detail="Team not found")
    # Basic registration check: both must have contact number
    if not a.get("contact_number") or not b.get("contact_number"):
        raise HTTPException(status_code=400, detail="Teams must complete registration to chat")

    m = Message(from_team_id=payload.from_team_id, to_team_id=payload.to_team_id, text=payload.text)
    inserted_id = create_document("message", m)
    return {"ok": True, "id": inserted_id}


@app.get("/chat/{team_a}/{team_b}", response_model=list)
def get_conversation(team_a: str, team_b: str):
    msgs = get_documents(
        "message",
        {"$or": [
            {"from_team_id": team_a, "to_team_id": team_b},
            {"from_team_id": team_b, "to_team_id": team_a},
        ]},
    )
    for m in msgs:
        m["id"] = str(m.pop("_id", ""))
    msgs.sort(key=lambda x: x.get("created_at", ""))
    return msgs


# ---------------------------
# Admin Basics
# ---------------------------
@app.get("/admin/stats", response_model=dict)
def admin_stats():
    teams = db["team"].count_documents({}) if db else 0
    posts = db["matchpost"].count_documents({}) if db else 0
    return {"total_teams": teams, "total_match_posts": posts}


@app.delete("/admin/teams/{team_id}", response_model=dict)
def admin_delete_team(team_id: str):
    res = db["team"].delete_one({"team_id": team_id})
    return {"deleted": res.deleted_count == 1}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
