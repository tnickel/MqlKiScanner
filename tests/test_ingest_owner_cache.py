"""Cache directories preserve source ownership across aliases and old paths."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from mqlkiscanner import config, db, downloader_client, ingest


def test_equal_sanitized_aliases_have_distinct_uid_owned_cache_directories():
    a = {"id": 1, "kuerzel": "a/b", "quellen_uid": "a/b"}
    b = {"id": 2, "kuerzel": "a b", "quellen_uid": "a b"}
    first, second = ingest._kuerzel_verzeichnis(a), ingest._kuerzel_verzeichnis(b)
    assert first != second
    assert first.name == "owner-" + sha256(b"a/b").hexdigest()
    assert second.name == "owner-" + sha256(b"a b").hexdigest()
    assert first.parent == second.parent == config.DATA_DIR / "quellen"


def test_alias_rename_and_explicit_transport_replacement_keep_owner_directory():
    source_id = db.add_quelle("before", "Before", "http://localhost:1")
    before = db.get_quelle(source_id)
    path = ingest._kuerzel_verzeichnis(before)
    db.update_quelle(source_id, kuerzel="after", base_url="http://localhost:2")
    assert ingest._kuerzel_verzeichnis(db.get_quelle(source_id)) == path
    db.delete_quelle(source_id)
    mirror_id = db.add_quelle("mirror", "Mirror", "http://localhost:3", quellen_uid=before["quellen_uid"])
    assert ingest._kuerzel_verzeichnis(db.get_quelle(mirror_id)) == path


def test_real_registered_sources_with_colliding_aliases_never_overwrite_same_id_bytes():
    first = db.get_quelle(db.add_quelle("a/b", "First", "http://localhost:1"))
    second = db.get_quelle(db.add_quelle("a b", "Second", "http://localhost:2"))

    class Bytes:
        def __init__(self, payload):
            self.payload = payload
        def trades_csv(self, *args):
            return self.payload

    first_path, _ = ingest.hole_trades(first, 7, "mql5", client=Bytes(b"first-source"))
    second_path, _ = ingest.hole_trades(second, 7, "mql5", client=Bytes(b"second-source"))
    assert first_path != second_path
    assert Path(first_path).read_bytes() == b"first-source"
    assert Path(second_path).read_bytes() == b"second-source"
    assert db.get_quellen_artefakt(first["id"], 7, "mql5", "trades")["sha256"] == sha256(b"first-source").hexdigest()


@pytest.mark.parametrize("first,second", [("UID", "uid"), ("a/b", "a b"),
    ("é", "e\u0301"), ("..\\outside", "../outside")])
def test_exact_distinct_uids_cannot_collapse_or_traverse(first, second):
    paths = [ingest._kuerzel_verzeichnis({"quellen_uid": uid}) for uid in (first, second)]
    assert paths[0] != paths[1]
    assert all(p.resolve().parent == (config.DATA_DIR / "quellen").resolve() for p in paths)


def test_synthetic_uidless_fallback_is_distinct_and_never_registers_an_owner():
    first = {"id": 1, "kuerzel": "a/b", "base_url": "http://localhost:1"}
    second = {"id": 1, "kuerzel": "a b", "base_url": "http://localhost:1"}
    original = dict(first)
    p1, p2 = ingest._kuerzel_verzeichnis(first), ingest._kuerzel_verzeichnis(second)
    assert p1 != p2 and p1.name.startswith("unverified-")
    assert ingest._kuerzel_verzeichnis(first) == p1
    assert first == original and not db.DB_PATH.exists()
    assert p1 != ingest._kuerzel_verzeichnis({**first, "quellen_uid": "a/b"})


@pytest.mark.parametrize("art", ["trades", "metrics"])
def test_new_owner_cache_path_keeps_stored_legacy_artifacts_readable(art, tmp_path):
    source_id = db.add_quelle("legacy", "Legacy", "http://localhost:1")
    source = db.get_quelle(source_id)
    old_dir = config.DATA_DIR / "quellen" / "legacy"
    old_dir.mkdir(parents=True)
    payload = b"Time;Type;Symbol\n" if art == "trades" else b'{"metrics": {"Currency": "USD"}}'
    old_file = old_dir / ("trades.csv" if art == "trades" else "metrics.json")
    old_file.write_bytes(payload)
    db.store_quellen_artefakt(source_id, 7, "mql5", art, sha256(payload).hexdigest(), str(old_file))

    class Offline:
        def trades_csv(self, *args):
            raise downloader_client.DownloaderConnectionError("offline")
        def metrics(self, *args):
            raise downloader_client.DownloaderConnectionError("offline")

    if art == "trades":
        path, changed = ingest.hole_trades(source, 7, "mql5", client=Offline())
        assert Path(path) == old_file and changed is False
    else:
        assert ingest.hole_metrics(source, 7, "mql5", client=Offline()) == {"metrics": {"Currency": "USD"}}
    assert old_file.read_bytes() == payload
    assert Path(db.get_quellen_artefakt(source_id, 7, "mql5", art)["path"]) == old_file
    assert ingest._kuerzel_verzeichnis(source) != old_dir
