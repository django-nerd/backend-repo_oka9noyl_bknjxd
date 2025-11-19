"""
Database Schemas for FindRivals

Each Pydantic model represents a collection in MongoDB. The collection name
is the lowercase of the class name.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# ---------------------------
# Core Domain Schemas
# ---------------------------
Sport = Literal["cricket", "football", "kabaddi", "shuttle", "tennis"]
TimeSlot = Literal["morning", "afternoon", "evening"]
ContactPref = Literal["call", "text"]


class Team(BaseModel):
    team_name: str = Field(..., description="Team name")
    sport: Sport = Field(..., description="Primary sport")
    players: List[str] = Field(default_factory=list, description="List of player names")
    location_name: Optional[str] = Field(None, description="Area or place name")
    latitude: Optional[float] = Field(None, description="Latitude for geofilters")
    longitude: Optional[float] = Field(None, description="Longitude for geofilters")
    contact_preference: ContactPref = Field(..., description="Preferred contact method")
    contact_number: str = Field(..., description="Phone number")
    availability: List[TimeSlot] = Field(default_factory=list, description="Available times of day")
    team_id: str = Field(..., description="Auto-generated team identifier like CRK-129")


class Matchpost(BaseModel):
    team_id: str = Field(..., description="Posting team ID")
    sport: Sport = Field(..., description="Sport for the match")
    num_players: int = Field(..., ge=1, description="Number of players needed")
    time_pref: TimeSlot = Field(..., description="Preferred time slot")
    note: Optional[str] = Field(None, description="Optional note")
    location_name: Optional[str] = Field(None)
    latitude: Optional[float] = Field(None)
    longitude: Optional[float] = Field(None)


class Message(BaseModel):
    from_team_id: str = Field(...)
    to_team_id: str = Field(...)
    text: str = Field(..., min_length=1, max_length=2000)
