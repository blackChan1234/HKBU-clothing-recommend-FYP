import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import server
from database import Base


class AuthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        server.app.dependency_overrides[server.get_db] = override_get_db
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        server.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def test_register_returns_token_and_username(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "secret123"},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["username"], "alice")
        self.assertEqual(body["token_type"], "bearer")
        self.assertTrue(body["access_token"])

    def test_register_duplicate_username_returns_409(self):
        payload = {"username": "alice", "password": "secret123"}

        first = self.client.post("/api/auth/register", json=payload)
        second = self.client.post("/api/auth/register", json=payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], "Username already taken.")

    def test_login_rejects_invalid_password(self):
        self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "secret123"},
        )

        response = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid username or password.")

    def test_register_returns_manual_login_message_when_token_creation_fails(self):
        with patch("server.create_access_token", side_effect=RuntimeError("broken token")):
            response = self.client.post(
                "/api/auth/register",
                json={"username": "alice", "password": "secret123"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "Account created, but automatic sign-in failed. Please log in manually.",
        )

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "secret123"},
        )
        self.assertEqual(login_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
