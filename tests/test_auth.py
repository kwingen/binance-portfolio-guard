"""认证/安全测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.auth import (
    hash_password, verify_password, validate_password_strength,
    create_access_token,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "ValidP@ss1"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)
        assert not verify_password("wrong", hashed)

    def test_different_hashes(self):
        h1 = hash_password("Test1234!")
        h2 = hash_password("Test1234!")
        assert h1 != h2  # bcrypt salting


class TestPasswordStrength:
    def test_valid(self):
        ok, _ = validate_password_strength("ValidP@ss1")
        assert ok

    def test_too_short(self):
        ok, err = validate_password_strength("Ab1!")
        assert not ok
        assert "8 位" in err

    def test_no_uppercase(self):
        ok, err = validate_password_strength("validp@ss1")
        assert not ok
        assert "大写" in err

    def test_no_lowercase(self):
        ok, err = validate_password_strength("VALIDP@SS1")
        assert not ok
        assert "小写" in err

    def test_no_digit(self):
        ok, err = validate_password_strength("ValidP@ssword")
        assert not ok
        assert "数字" in err

    def test_no_special(self):
        ok, err = validate_password_strength("ValidPass1")
        assert not ok
        assert "特殊" in err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
