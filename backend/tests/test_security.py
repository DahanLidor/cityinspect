"""
Tests for security helpers: password hashing and JWT.
"""
import pytest
from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_hash_verify_correct():
    h = hash_password("secret")
    assert verify_password("secret", h) is True


def test_hash_verify_wrong():
    h = hash_password("secret")
    assert verify_password("wrongpass", h) is False


def test_hash_is_different_each_time():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # Argon2 uses random salt


def test_create_decode_token():
    token = create_access_token("testuser")
    assert decode_token(token) == "testuser"


def test_decode_invalid_token():
    assert decode_token("not.a.valid.token") is None


def test_decode_empty_token():
    assert decode_token("") is None


def test_decode_tampered_token():
    token = create_access_token("user1")
    tampered = token[:-5] + "XXXXX"
    assert decode_token(tampered) is None
