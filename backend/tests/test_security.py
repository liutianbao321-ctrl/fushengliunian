from app.utils.security import get_password_hash, verify_password


def test_passwords_use_argon2id_and_verify() -> None:
    password_hash = get_password_hash("production-test-password")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("production-test-password", password_hash)
    assert not verify_password("wrong-password", password_hash)
