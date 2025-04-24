from sqlalchemy import Column, Integer, String, Boolean, Float, JSON, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    bungie_id = Column(String, unique=True)
    access_token = Column(String)
    refresh_token = Column(String)
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

def init_db(database_url='sqlite:///catalysts.db'):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session() 