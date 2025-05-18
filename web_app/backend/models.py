from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, ForeignKey, create_engine, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
import uuid
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy import Text, Index
import json

Base = declarative_base()

# --- SQLAlchemy Models --- 
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    bungie_id = Column(String, unique=True, index=True)
    supabase_uuid = Column(String, unique=True, index=True, nullable=True)
    access_token = Column(String)
    refresh_token = Column(String)
    access_token_expires = Column(DateTime)
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

class Conversation(Base):
    """Represents a single conversation thread."""
    __tablename__ = 'conversations'

    # Using UUID for primary key
    id = Column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_bungie_id = Column(String, nullable=False, index=True) # Index for faster lookup
    title = Column(String, nullable=True) # Initially null, populated by summarization
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    archived = Column(Boolean, default=False, nullable=False)  # New column for archiving

    # Relationship to messages
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.order_index")

    def __repr__(self):
        return f"<Conversation(id={self.id}, user='{self.user_bungie_id}', title='{self.title}')>"

class Message(Base):
    """Represents a single message within a conversation."""
    __tablename__ = 'messages'

    id = Column(UUIDType(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUIDType(as_uuid=True), ForeignKey('conversations.id'), nullable=False, index=True)
    order_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to the conversation
    conversation = relationship("Conversation", back_populates="messages")

    # Optional: Add an index for conversation_id and order_index together if performance requires
    # __table_args__ = (Index('ix_message_conv_order', 'conversation_id', 'order_index'), )

    def __repr__(self):
        return f"<Message(id={self.id}, conv_id={self.conversation_id}, role='{self.role}', order={self.order_index})>"

class WeaponPerkDetail(BaseModel):
    perk_hash: int # The Bungie manifest hash for the perk (DestinyInventoryItemDefinition)
    name: str
    description: Optional[str] = "" # Perk's description
    icon_url: HttpUrl # Perk's icon

class Weapon(BaseModel):
    item_hash: str # Keep as string to match current usage, conversion happens at DB
    instance_id: Optional[str] = None
    name: str
    description: Optional[str] = ""
    icon_url: Optional[HttpUrl] = None # Changed to HttpUrl for validation
    tier_type: Optional[str] = None
    item_type: Optional[str] = None # e.g., "Auto Rifle"
    item_sub_type: Optional[str] = None # e.g., "Aggressive Frame"
    damage_type: Optional[str] = "None" # Kinetic, Arc, Solar, Void, Stasis, Strand
    
    # NEW STRUCTURED PERKS
    barrel_perks: List[WeaponPerkDetail] = Field(default_factory=list)
    magazine_perks: List[WeaponPerkDetail] = Field(default_factory=list)
    trait_perk_col1: List[WeaponPerkDetail] = Field(default_factory=list) # Typically 3rd column
    trait_perk_col2: List[WeaponPerkDetail] = Field(default_factory=list) # Typically 4th column
    # Optional: For future expansion or more detailed categorization
    origin_trait: Optional[WeaponPerkDetail] = None
    # masterwork_applied: Optional[WeaponPerkDetail] = None # If we want to store the specific MW applied
    # mod_applied: Optional[WeaponPerkDetail] = None

    # Location and other metadata
    location: Optional[str] = None  # e.g., "Vault", "Character X Inventory", "Character Y Equipped"
    is_equipped: bool = False # Calculated if location indicates equipped
    power_level: Optional[int] = None # Current power level of the item instance
    # last_updated: datetime = Field(default_factory=datetime.utcnow) # For cache management in DB

    class Config:
        populate_by_name = True
        # alias_generator = to_snake # If converting from camelCase API responses

class CatalystObjective(BaseModel):
    objective_hash: int
    name: str
    description: str
    completion_value: int
    progress: int
    is_complete: bool

class CatalystData(BaseModel):
    item_hash: int # Changed from record_hash as it's an item
    name: str
    description: str
    icon_url: str # Added from previous discussions
    # source: Optional[str] = None # Retaining for now, might be populated from manifest
    is_complete: bool
    objectives: List[CatalystObjective]
    #bungie_provided_desc: Optional[str] = None # Field for Bungie's description
    #user_notes: Optional[str] = None # Field for user notes

class UserResponse(BaseModel):
    status: str
    bungie_id: str

class CallbackData(BaseModel):
    code: str

def init_db(database_url='sqlite:///./catalysts.db'):
    # global SessionLocal # No longer modifying a global here
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    # Create the sessionmaker locally
    LocalSessionMaker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Create tables defined by SQLAlchemy models (User, Catalyst, etc.)
    Base.metadata.create_all(bind=engine)
    print(f"Initialized SQLite tables for {database_url} (if they didn't exist).")
    # Return the engine AND the configured sessionmaker
    return engine, LocalSessionMaker

CHAT_HISTORY_DATABASE_URL = "sqlite:///./web_app/backend/chat_history.db" # Point inside backend

chat_history_engine = create_engine(
    CHAT_HISTORY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Session factory specifically for chat history
ChatHistorySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=chat_history_engine)

def init_chat_history_db():
    """Initializes the chat history database and creates tables if they don't exist."""
    # Create tables related ONLY to chat history using the new engine
    # We pass the specific tables to create_all to avoid touching other tables
    Base.metadata.create_all(
        bind=chat_history_engine,
        tables=[Conversation.__table__, Message.__table__] # Explicitly list tables
    )
    print(f"Initialized chat history tables for {CHAT_HISTORY_DATABASE_URL} (if they didn't exist).")

class ChatMessageBase(BaseModel):
    role: str = Field(validation_alias='sender') # Alias for 'sender' column from Supabase
    content: str

class ChatMessageSchema(ChatMessageBase):
    id: uuid.UUID
    timestamp: datetime = Field(validation_alias='created_at') # Alias for 'created_at' column from Supabase
    order_index: int
    model_config = ConfigDict(from_attributes=True, populate_by_name=True) # Ensure populate_by_name is True

class ConversationBase(BaseModel):
    title: Optional[str] = None

class ConversationCreate(ConversationBase):
    user_bungie_id: str # Needed when creating

class ConversationSchema(ConversationBase):
    id: uuid.UUID
    user_bungie_id: str = Field(validation_alias='user_id')
    created_at: datetime
    updated_at: datetime
    archived: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True, populate_by_name=True) 