import pytest
import postbag_mcp
from test_postbag import bag, be, joined


def test_service_sends_from_outside_a_session_only_to_its_grant(joined, be):
    original = joined.ledger_path().read_bytes()
    grant = joined.grant_service("whatsapp")
    assert joined.ledger_path().read_bytes() == original
    assert grant["token"] not in joined.ledger_path().read_text()
    assert "service-grant" not in joined.ledger_path().read_text()
    assert grant["token"] not in joined.ledger_path().with_suffix(".services.json").read_text()
    be(None)
    with pytest.raises(joined.Refusal):
        joined.send("claude", "notice")
    receipt = joined.send("claude", "Watch W has new replies", final=True,
                          service="whatsapp", service_token=grant["token"])
    assert receipt["from"] == "whatsapp"
    assert "Watch W has new replies" in joined.KNOCKED[-1][2]
    assert "Service notice" in joined.KNOCKED[-1][2]
    assert joined.Snapshot(joined.records()).peers.keys() == {"claude", "codex"}
    with pytest.raises(joined.Refusal, match="service grant"):
        joined.send("codex", "notice", service="whatsapp", service_token=grant["token"])


def test_service_rotation_revocation_and_rejoin_invalidate_capability(joined, be):
    first = joined.grant_service("whatsapp")
    second = joined.grant_service("whatsapp")
    be(None)
    with pytest.raises(joined.Refusal, match="service grant"):
        joined.check_service("whatsapp", "claude", first["token"])
    joined.check_service("whatsapp", "claude", second["token"])
    be("claude")
    joined.grant_service("whatsapp", ttl=0)
    with pytest.raises(joined.Refusal, match="service grant"):
        joined.check_service("whatsapp", "claude", second["token"])
    third = joined.grant_service("whatsapp")
    joined.join("claude")
    with pytest.raises(joined.Refusal, match="service grant"):
        joined.check_service("whatsapp", "claude", third["token"])


def test_grant_requires_receiving_session_and_read_hides_hash(joined, be, capsys):
    grant = joined.grant_service("whatsapp")
    joined.read(None)
    assert "whatsapp" in capsys.readouterr().out
    data = postbag_mcp.read_data(100, None)
    assert "token_hash" not in str(data)
    assert grant["token"] not in str(data)
    be(None)
    with pytest.raises(joined.Refusal):
        joined.grant_service("whatsapp")


def test_structured_service_receipt_distinguishes_refusal_and_submission(joined, be, monkeypatch, capsys):
    import json
    grant = joined.grant_service("whatsapp")
    capsys.readouterr()
    be(None)
    monkeypatch.setenv("POSTBAG_SERVICE_TOKEN", grant["token"])
    joined.main(["service-send", "whatsapp", "claude", "Watch W updated", "--json"])
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["ok"] and receipt["submission_state"] == "submitted"
    monkeypatch.setenv("POSTBAG_SERVICE_TOKEN", "invalid")
    with pytest.raises(SystemExit):
        joined.main(["service-send", "whatsapp", "claude", "notice", "--json"])
    receipt = json.loads(capsys.readouterr().out)
    assert not receipt["ok"] and receipt["submission_state"] == "not_submitted"


def test_registry_refuses_symlinks_and_other_users_access(joined, tmp_path):
    import os
    target = tmp_path / "elsewhere"
    target.write_text("{}")
    registry = joined.ledger_path().with_suffix(".services.json")
    registry.symlink_to(target)
    with pytest.raises(OSError):
        joined.grant_service("whatsapp")
    registry.unlink()
    registry.write_text("{}")
    registry.chmod(0o644)
    with pytest.raises(joined.Refusal, match="owner-private"):
        joined.grant_service("whatsapp")


def test_codex_is_discovered_with_service_manager_path(monkeypatch):
    import postbag
    monkeypatch.delenv("POSTBAG_CODEX", raising=False)
    monkeypatch.setattr(postbag.shutil, "which", lambda _: None)
    monkeypatch.setattr(postbag.os, "access", lambda path, _: path == "/opt/homebrew/bin/codex")
    assert postbag.codex_path() == "/opt/homebrew/bin/codex"
