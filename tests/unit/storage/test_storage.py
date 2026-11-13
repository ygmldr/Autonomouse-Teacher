import json
from dataclasses import replace
import sqlite3

import pytest

from autoteacher_m0.contracts import RunRecord
from autoteacher_m0.storage.artifacts import ArtifactStore, sanitize
from autoteacher_m0.storage.schema import RunStore


def record():
    return RunRecord("run-a", "case-a", "teacher_v0", "session-a", "deepseek-official",
                     "safe text", "SUCCESS", [], metadata={"mode": "mock"})


def test_nested_redaction_and_invented_sentinel():
    value = {"api_key": "INVENTED_ONLY", "nested": ["Bearer INVENTED_TOKEN", "sk-FAKE_ONLY"],
             "text": "nonce TEST_SENTINEL password=FAKE_ONLY"}
    encoded = json.dumps(sanitize(value, sentinels=("TEST_SENTINEL",)))
    for forbidden in ("INVENTED_ONLY", "INVENTED_TOKEN", "sk-FAKE_ONLY", "TEST_SENTINEL", "FAKE_ONLY"):
        assert forbidden not in encoded
    assert "[REDACTED]" in encoded
    keys = sanitize({"sk-FAKE_ONLY": "ordinary", "TEST_SENTINEL": "ordinary"},
                    sentinels=("TEST_SENTINEL",))
    assert "sk-FAKE_ONLY" not in json.dumps(keys)
    assert "TEST_SENTINEL" not in json.dumps(keys)
    assert len(keys) == 2


def test_json_artifact_roundtrip_and_no_overwrite(tmp_path):
    store = ArtifactStore(tmp_path)
    target = store.save(record())
    assert target.is_file()
    assert store.load("run-a") == record()
    with pytest.raises(FileExistsError):
        store.save(record())
    with pytest.raises(ValueError):
        store.load("../outside")


def test_sqlite_roundtrip_no_overwrite_or_sql_injection(tmp_path):
    with RunStore(tmp_path / "runs.sqlite3") as store:
        store.save(record())
        assert store.load("run-a") == record()
        with pytest.raises(KeyError):
            store.load("' OR 1=1 --")
        with pytest.raises(sqlite3.IntegrityError):
            store.save(record())


def test_json_quoted_keys_and_index_identifiers_are_protected(tmp_path):
    assert "INVENTED_ONLY" not in sanitize('{"api_key":"INVENTED_ONLY"}')
    with RunStore(tmp_path / "runs.sqlite3") as store:
        with pytest.raises(ValueError):
            store.save(replace(record(), session_id="sk-FAKE_ONLY"))
    assert b"sk-FAKE_ONLY" not in (tmp_path / "runs.sqlite3").read_bytes()
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path).save(replace(record(), run_id="sk-FAKE_ONLY"))


def test_arbitrary_sdk_object_not_serializable():
    with pytest.raises(TypeError):
        sanitize(object())
