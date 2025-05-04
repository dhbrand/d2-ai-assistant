from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, ForeignKey, create_engine, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    bungie_id = Column(String, unique=True, index=True)
    access_token = Column(String)
    refresh_token = Column(String)
    access_token_expires = Column(DateTime)
    token_expiry = Column(Integer)
    catalysts = relationship('Catalyst', back_populates='user')

class Catalyst(Base):
    __tablename__ = 'catalysts'

    id = Column(Integer, primary_key=True)
    record_hash = Column(String)
    name = Column(String)
    description = Column(String)
    weapon_type = Column(String)
    objectives = Column(JSON)
    complete = Column(Boolean, default=False)
    progress = Column(Float, default=0.0)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='catalysts')

# --- Pydantic Models for API Responses ---

class Weapon(BaseModel):
    item_hash: str  # Changed from int to str to match API response
    instance_id: Optional[str] = None
    name: str 
    description: str
    icon_url: str
    tier_type: str  # e.g., Exotic, Legendary
    item_type: str  # e.g., Auto Rifle, Hand Cannon
    item_sub_type: str
    location: Optional[str] = None
    is_equipped: Optional[bool] = False
    damage_type: Optional[str] = "None"
    
    class Config:
        orm_mode = False
        
    @classmethod
    def from_dict(cls, raw_data: dict):
        """Convert raw weapon data to a Weapon model instance."""
        # Default values for all required fields
        weapon_data = {
            "item_hash": str(raw_data.get("item_hash", "")),
            "instance_id": raw_data.get("instance_id", ""),
            "name": raw_data.get("name", "Unknown Weapon"),
            "description": raw_data.get("description", "No description available"),
            "icon_url": raw_data.get("icon_url", ""),
            "tier_type": raw_data.get("tier_type", "Common"),
            "item_type": raw_data.get("item_type", "Unknown"),
            "item_sub_type": raw_data.get("item_sub_type", ""),
            "location": raw_data.get("location", ""),
            "is_equipped": raw_data.get("is_equipped", False),
            "damage_type": raw_data.get("damage_type", "None")
        }
        return cls(**weapon_data)

class CatalystObjective(BaseModel):
    description: str
    completion: int
    progress: int
    complete: bool
    model_config = ConfigDict(from_attributes=True)

class CatalystData(BaseModel):
    name: str
    description: str
    weapon_type: str
    objectives: List[CatalystObjective]
    complete: bool
    progress: float
    model_config = ConfigDict(from_attributes=True)

class UserResponse(BaseModel):
    status: str
    bungie_id: str

class CallbackData(BaseModel):
    code: str

def init_db(database_url='sqlite:///./catalysts.db'):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal 