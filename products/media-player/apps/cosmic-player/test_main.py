"""Media Player identity, full native sources and exact OS service boundary."""

import json
from pathlib import Path
import tomllib

from test_support import load_local_module

PRODUCT = Path(__file__).resolve().parents[2]
ROOT = PRODUCT.parents[1]
NATIVE = PRODUCT / "native/cosmic-player"
MANIFEST = Path(__file__).with_name("app.json")


def test_seven_tools_keep_identity_and_separate_observation_from_control():
    manifest = json.loads(MANIFEST.read_text())
    assert (manifest["id"], manifest["runtime"], manifest["schema_version"]) == (
        "cosmic-player", "binary", 2,
    )
    assert manifest["mcp"]["entry"] == "/usr/bin/cosmic-player"
    tools = {tool["name"]: tool for tool in manifest["mcp"]["tools"]}
    assert set(tools) == {f"player.{name}" for name in (
        "play", "pause", "stop", "next", "previous", "toggle", "status",
    )}
    for name, tool in tools.items():
        assert tool["args"] == []
        assert tool["needs"] == [{
            "verb": "desktop.media.observe" if name == "player.status" else "desktop.media.control",
            "scope": {"kind": "fixed", "scope": {"kind": "name", "value": "cosmic-player"}},
            "why": {"en": (
                "Read playback status and track metadata from this owner's native Media Player."
                if name == "player.status" else "Control playback in this owner's native Media Player."
            )},
        }]
    assert "whichever" not in MANIFEST.read_text()
    assert "active MPRIS" not in MANIFEST.read_text()


def test_native_staging_keeps_original_resources_modes_and_separate_renderer(tmp_path):
    stage = load_local_module(ROOT / "tools/stage.py", "player_stage")
    native = load_local_module(ROOT / "tools/stage_native.py", "player_stage_native")
    assert stage.stage("media-player", tmp_path / "installed") == ["cosmic-player"]
    app = tmp_path / "installed/usr/lib/cos/apps/cosmic-player"
    assert (app / "app.json").read_bytes() == MANIFEST.read_bytes()
    assert not (app / "test_main.py").exists()
    assert not (tmp_path / "installed/usr/bin").exists()
    assert native.stage("media-player", tmp_path / "native") == ["cosmic-player"]
    target = tmp_path / "native/cosmic-player"
    for source in NATIVE.rglob("*"):
        if source.is_file():
            copied = target / source.relative_to(NATIVE)
            assert copied.read_bytes() == source.read_bytes()
            assert copied.stat().st_mode & 0o777 == source.stat().st_mode & 0o777
    assert (target / "LICENSE").read_bytes() == (PRODUCT / "native/LICENSE").read_bytes()
    assert len(list((target / "i18n").glob("*/*.ftl"))) == 72
    for relative in (
        "res/com.clawos.Player.desktop", "res/com.clawos.Player.metainfo.xml",
        "res/com.clawos.Player.thumbnailer", "res/icons/hicolor/scalable/apps/com.clawos.Player.svg",
        "src/video.rs", "src/project.rs", "src/thumbnail.rs", "src/xdg_portals.rs",
        "build.rs", "shell.nix", "rustfmt.toml", "debian/control", "Cargo.lock",
    ):
        assert (target / relative).is_file(), relative
    build = load_local_module(ROOT / "tools/native_build.py", "player_native_build")
    build.prepare("media-player", tmp_path / "platform/desktop/toolkit", tmp_path / "prepared")
    cargo = tomllib.loads((tmp_path / "prepared/Cargo.toml").read_text())
    assert cargo["dependencies"]["claw-os-sdk"]["path"] == str(tmp_path / "platform/claw-os-sdk/rust")
    assert cargo["dependencies"]["libcosmic"]["git"] == "https://github.com/pop-os/libcosmic.git"
    assert cargo["dependencies"]["iced_video_player"]["git"] == "https://github.com/wash2/iced_video_player.git"
    assert cargo["dependencies"]["iced_video_player"]["branch"] == "iced-rebase"
    assert cargo["features"]["default"] == ["mpris-server", "xdg-portal", "wgpu", "wayland"]
    assert "patch" not in cargo
    assert (tmp_path / "prepared/Cargo.lock").read_bytes() == (NATIVE / "Cargo.lock").read_bytes()
    assert "cargo:rerun-if-changed=target/xdgen" in (NATIVE / "build.rs").read_text()
    assert not (target / "core").exists()
    assert not (target / "toolkit").exists()


def test_native_mcp_and_ui_share_the_fixed_live_playback_boundary():
    mcp = (NATIVE / "src/mcp.rs").read_text()
    assert '"/usr/local/bin/cos"' in mcp
    assert "cos_call_json_async_with_binary" in mcp
    assert "spawn_blocking" not in mcp
    assert '"__media-player"' in mcp
    assert "context.cancelled()" in mcp
    for forbidden in ("Connection::session", "ListNames", "with_player", 'cos app', "CLAW_COS_BIN"):
        assert forbidden not in mcp
    backend = (NATIVE / "src/mpris_backend.rs").read_text()
    assert '&format!("com.clawos.Player.pid{}", process::id())' in backend
    assert '&format!("org.mpris.MediaPlayer2.' not in backend
    assert "self.message(PlaybackCommand::Stop).await" in backend
    ui = (NATIVE / "src/main.rs").read_text()
    assert "VideoPlayer::new(video)" in ui
    assert "Message::MprisCommand(command)" in ui
    assert "self.update(command.into())" in ui
    assert "video.seek(Duration::ZERO, true)" in ui
    assert "stopped: self.stopped || self.video_opt.is_none()" in ui
    assert "new.stopped |= video.eos()" in ui
    assert "self.video_opt.as_ref().and(self.flags.url_opt.clone())" in ui
    assert (PRODUCT / "native/test_process.py").is_file()
    assert (NATIVE / "test/support/mpris.rs").is_file()


def test_product_navigation_and_native_ci_use_the_exact_player_identity():
    package = json.loads((PRODUCT / "package.json").read_text())
    assert package["apps"] == ["apps/cosmic-player"]
    assert package["native"] == {"cosmic-player": "native/cosmic-player"}
    assert package["native_kind"] == "binary"
    assert package["native_process_test"] == "native/test_process.py"
    assert package["native_assets"] == {"cosmic-player": {"app.json": "apps/cosmic-player/app.json"}}
    assert "products/media-player" in (ROOT / "README.md").read_text()
    assert "`products/media-player/`" in (ROOT / "ARCHITECTURE.md").read_text()
    assert "same live native playback session" in (PRODUCT / "README.md").read_text()
    assert "1c7756e7ce076ff80e8f94a6c506c10212a25f60" in (PRODUCT / "PROVENANCE.md").read_text()
    workflow = (ROOT / ".github/workflows/test.yml").read_text()
    assert "if: matrix.product == 'media-player'" in workflow
    assert "python3 tools/native_build.py media-player build" in workflow
    assert "python3 products/media-player/native/test_process.py" in workflow
