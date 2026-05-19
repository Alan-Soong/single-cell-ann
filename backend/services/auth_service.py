from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash


ALLOWED_ROLES = {"normal_user", "researcher", "data_manager", "admin"}


@dataclass
class AuthUser:
    username: str
    role: str
    created_at: str

    def summary(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
        }


class AuthService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._tokens: dict[str, str] = {}

    def register(self, users_path: Path, username: str, password: str, role: str = "researcher") -> dict[str, Any]:
        username = username.strip()
        role = role.strip() or "researcher"
        self._validate_credentials(username, password)
        if role not in ALLOWED_ROLES:
            raise ValueError(f"unsupported role: {role}")

        with self._lock:
            store = self._load_store(users_path)
            if username in store["users"]:
                raise ValueError("username already exists")

            user = {
                "username": username,
                "password_hash": generate_password_hash(password),
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            store["users"][username] = user
            self._save_store(users_path, store)
            return {"authenticated": True, "user": self._public_user(user)}

    def login(self, users_path: Path, username: str, password: str) -> dict[str, Any]:
        username = username.strip()
        with self._lock:
            store = self._load_store(users_path)
            user = store["users"].get(username)
            if user is None or not check_password_hash(user["password_hash"], password):
                raise ValueError("invalid username or password")

            token = secrets.token_urlsafe(32)
            self._tokens[token] = username
            return {"authenticated": True, "token": token, "user": self._public_user(user)}

    def logout(self, token: str | None) -> dict[str, Any]:
        with self._lock:
            if token:
                self._tokens.pop(token, None)
        return {"authenticated": False}

    def current_user(self, users_path: Path, token: str | None) -> dict[str, Any]:
        if not token:
            return {"authenticated": False, "user": None}

        with self._lock:
            username = self._tokens.get(token)
            if username is None:
                return {"authenticated": False, "user": None}
            store = self._load_store(users_path)
            user = store["users"].get(username)
            if user is None:
                self._tokens.pop(token, None)
                return {"authenticated": False, "user": None}
            return {"authenticated": True, "user": self._public_user(user)}

    @staticmethod
    def token_from_header(authorization: str | None) -> str | None:
        if not authorization:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return token.strip()

    @staticmethod
    def _validate_credentials(username: str, password: str) -> None:
        if len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if len(password) < 6:
            raise ValueError("password must be at least 6 characters")

    @staticmethod
    def _load_store(users_path: Path) -> dict[str, Any]:
        if not users_path.exists():
            return {"users": {}}
        with users_path.open("r", encoding="utf-8") as file:
            store = json.load(file)
        if not isinstance(store.get("users"), dict):
            raise ValueError("invalid users store")
        return store

    @staticmethod
    def _save_store(users_path: Path, store: dict[str, Any]) -> None:
        users_path.parent.mkdir(parents=True, exist_ok=True)
        with users_path.open("w", encoding="utf-8") as file:
            json.dump(store, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _public_user(user: dict[str, Any]) -> dict[str, Any]:
        return AuthUser(
            username=user["username"],
            role=user["role"],
            created_at=user["created_at"],
        ).summary()


auth_service = AuthService()
