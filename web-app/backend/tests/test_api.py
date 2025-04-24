import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..main import app, get_current_user
from ..models import Base, User, Catalyst

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_current_user():
    """Override the get_current_user dependency for testing"""
    db = TestingSessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(bungie_id="test_user", access_token="test_token")
            db.add(user)
            db.commit()
        return user
    finally:
        db.close()

app.dependency_overrides[get_current_user] = override_get_current_user

@pytest.fixture
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(test_db):
    return TestClient(app)

def test_read_main(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Destiny 2 Catalyst Tracker API"}

def test_get_auth_url(client):
    response = client.get("/auth/url")
    assert response.status_code == 200
    assert "auth_url" in response.json()

def test_get_catalysts(client):
    response = client.get("/catalysts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_verify_token(client):
    response = client.get("/auth/verify")
    assert response.status_code == 200
    assert response.json()["status"] == "valid" 