from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, ForeignKey, create_engine, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from typing import List, Optional
from datetime import datetime

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

def init_db(database_url='sqlite:///./catalysts.db'):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal 