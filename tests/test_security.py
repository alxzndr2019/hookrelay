from app.core.security import generate_api_key, hash_key, keys_match, parse_key


def test_generated_key_roundtrips():
    full_key, prefix, key_hash = generate_api_key()
    assert parse_key(full_key) == prefix
    assert hash_key(full_key) == key_hash


def test_keys_are_unique():
    assert generate_api_key()[0] != generate_api_key()[0]


def test_malformed_tokens_are_rejected():
    for bad in ["", "garbage", "hr_live_", "hr_live_abc_def", "hr_live_abcd1234", "hr_live_abcd1234_"]:
        assert parse_key(bad) is None


def test_hash_comparison():
    assert keys_match(hash_key("a"), hash_key("a"))
    assert not keys_match(hash_key("a"), hash_key("b"))