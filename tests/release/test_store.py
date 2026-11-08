from datetime import datetime, timedelta, timezone
import json
import subprocess

import pytest

import release_store as store
import release_snapshots as snapshots
from release_common import digest, write_json
from test_snapshots import runtime, app


def web_app(root):
    (root / "web").mkdir()
    (root / "web/index.html").write_text("<!doctype html><title>Store fixture</title>")
    (root / "web/app.js").write_text("window.fixture = true;")
    manifest = snapshots.read_metadata(root / "app.json")
    write_json(root / "web-ui.json", {
        "schema": "claw.web-app/v1", "app_id": manifest["id"], "source_kind": "product",
        "source_name": "fixture", "title": manifest["name"], "description": "",
        "entry": "web/index.html",
    })
    return root


def test_store_index_binds_signed_product_ui_and_immutable_release(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    root = sign(web_app(app()))
    snapshots.build_catalog([root], tmp_path / "snapshots", release_version="1.0.0",
                            architecture="all", provenance=verifier, signing=signing)
    index = store.compose([tmp_path / "snapshots"], tmp_path / "store", verifier, signing)
    record = index["apps"][0]
    assert record["web_ui"]["sha256"] == digest(root / "web-ui.json")
    assert record["release_tag"] == "app-fixture-v1.0.0"
    assert record["artifact"]["sha256"] in record["artifact"]["file"]
    assert store.verified_index(tmp_path / "store", signing) == index
    assert "permissions_granted" not in json.dumps(index)
    changed = dict(index)
    changed["expires_at"] = store.utc(datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(ValueError, match="freshness|expired"):
        store.validate_index(changed)
    changed = json.loads(json.dumps(index))
    changed["apps"][0]["release_tag"] = "app-different-v1.0.0"
    with pytest.raises(ValueError, match="official release"):
        store.validate_index(changed)
    (tmp_path / "store/index.json").write_text("{}")
    with pytest.raises(subprocess.CalledProcessError):
        store.verified_index(tmp_path / "store", signing)


def test_store_refresh_keeps_artifacts_and_advances_signed_freshness(tmp_path, runtime, signing, app):
    verifier, sign = runtime
    root = sign(web_app(app()))
    snapshots.build_catalog([root], tmp_path / "snapshots", release_version="1.0.0",
                            architecture="all", provenance=verifier, signing=signing)
    initial = store.compose([tmp_path / "snapshots"], tmp_path / "store", verifier, signing)
    refreshed = store.refresh(tmp_path / "store", signing)
    assert refreshed["apps"] == initial["apps"]
    assert int(refreshed["generation"]) > int(initial["generation"])
    assert store.verified_index(tmp_path / "store", signing) == refreshed


def test_publication_signs_exact_debian_app_payload_and_retains_web_assets(
    tmp_path, runtime, signing, app, deb,
):
    verifier, _ = runtime
    root = web_app(app())
    app_id = snapshots.read_metadata(root / "app.json")["id"]
    files = {f"usr/lib/cos/apps/{app_id}/{path.relative_to(root).as_posix()}": path.read_bytes()
             for path in root.rglob("*") if path.is_file()}
    artifact = deb("claw-app-fixture", files=files)
    plan = {"version": "1.0.0", "packages": [{
        "package": "claw-app-fixture", "architecture": "all",
        "selection": "fixture", "apps": [app_id],
    }]}
    groups = store.prepare_release_snapshots(
        plan, [artifact], tmp_path / "prepared", verifier, signing,
        tmp_path / "package-key.json",
    )
    record = store.snapshot_records(groups["fixture"][0], verifier, signing)[0]
    extracted = tmp_path / "extracted"
    snapshots.extract_archive(groups["fixture"][0] / record["artifact"]["file"], extracted)
    assert (extracted / "web/app.js").read_bytes() == (root / "web/app.js").read_bytes()
    assert (extracted / "app.json").read_bytes() == (root / "app.json").read_bytes()
    assert (extracted / ".provenance.json").is_file()
    assert record["provenance"]["publisher_key_id"] == verifier.publisher_key_id
