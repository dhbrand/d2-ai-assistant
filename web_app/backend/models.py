from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, ForeignKey, create_engine, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
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
    perks: List[str] = []
    
    model_config = ConfigDict(from_attributes=True)
        
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
            "damage_type": raw_data.get("damage_type", "None"),
            "perks": raw_data.get("perks", [])
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