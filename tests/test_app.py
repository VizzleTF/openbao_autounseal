"""Unit tests for the OpenBao auto-unseal controller.

The suite focuses on the configurable-TLS logic added in 0.5.12 and exercises
every OpenBao HTTP helper with a mocked ``requests`` so the ``verify=TLS_VERIFY``
paths are covered without a live cluster. The functions read module-level
globals that the real entrypoint sets in ``__main__``; the ``wired`` fixture
injects test doubles for them.
"""
from unittest.mock import MagicMock

import pytest

import app


# --------------------------------------------------------------------------- #
# resolve_tls_verify
# --------------------------------------------------------------------------- #
def test_tls_verify_default_skips(monkeypatch):
    monkeypatch.delenv("OPENBAO_CA_CERT", raising=False)
    monkeypatch.delenv("OPENBAO_TLS_SKIP_VERIFY", raising=False)
    assert app.resolve_tls_verify() is False


@pytest.mark.parametrize("value", ["false", "0", "no", "FALSE"])
def test_tls_verify_can_be_enabled(monkeypatch, value):
    monkeypatch.delenv("OPENBAO_CA_CERT", raising=False)
    monkeypatch.setenv("OPENBAO_TLS_SKIP_VERIFY", value)
    assert app.resolve_tls_verify() is True


def test_tls_verify_ca_cert_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENBAO_TLS_SKIP_VERIFY", "true")
    monkeypatch.setenv("OPENBAO_CA_CERT", "/etc/ca/bundle.pem")
    assert app.resolve_tls_verify() == "/etc/ca/bundle.pem"


def test_list_convert_stringifies_indices():
    assert app.list_convert(["a", "b"]) == {"0": "a", "1": "b"}


# --------------------------------------------------------------------------- #
# OpenBao HTTP helpers — cover the verify=TLS_VERIFY call sites
# --------------------------------------------------------------------------- #
@pytest.fixture
def wired(monkeypatch):
    """Inject the module globals the entrypoint normally sets, plus a fake
    requests and a no-op sleep, and force TLS verification on so the value is
    actually threaded into every call."""
    monkeypatch.setattr(app, "TLS_VERIFY", True, raising=False)
    monkeypatch.setattr(app, "auto_unseal_payload", {"secret_shares": 1, "secret_threshold": 1}, raising=False)
    monkeypatch.setattr(app, "status_init", 0, raising=False)
    monkeypatch.setattr(app, "status_unseal", 1, raising=False)
    monkeypatch.setattr(app, "status_ok", 2, raising=False)
    monkeypatch.setattr(app, "status_error", 3, raising=False)
    monkeypatch.setattr(app, "pod_retrieval_max_retries", 1, raising=False)
    monkeypatch.setattr(app, "namespace", "openbao", raising=False)
    monkeypatch.setattr(app, "root_token", "openbao-root-token", raising=False)
    monkeypatch.setattr(app, "openbao_keys", "openbao-keys", raising=False)
    monkeypatch.setattr(app, "read_secret", MagicMock(), raising=False)
    monkeypatch.setattr(app, "sleep", lambda *_a, **_k: None)
    fake = MagicMock()
    monkeypatch.setattr(app, "requests", fake)
    # requests.exceptions is consulted in except clauses; keep the real classes.
    import requests as real_requests
    fake.exceptions = real_requests.exceptions
    return fake


def test_init_openbao_passes_verify(wired):
    wired.put.return_value.json.return_value = {"root_token": "t", "keys": ["k"]}
    result = app.init_openbao("https://bao:8200")
    assert result == {"root_token": "t", "keys": ["k"]}
    assert wired.put.call_args.kwargs["verify"] is True


def test_openbao_unseal_passes_verify(wired):
    app.openbao_unseal("unseal-key", "https://bao:8200")
    assert wired.put.call_args.kwargs["verify"] is True


def test_get_seal_status_ok_path(wired):
    wired.get.return_value.json.return_value = {"initialized": True, "sealed": False}
    assert app.get_seal_status("https://bao:8200", True) == app.status_ok
    assert wired.get.call_args.kwargs["verify"] is True


def test_wait_for_quorum_joins_and_verifies(wired):
    wired.get.return_value.json.return_value = {"leader_address": "https://m:8200"}
    wired.get.return_value.status_code = 200
    app.wait_for_quorum(["https://m:8200", "https://r:8200"], "https://m:8200")
    # leader GET and raft-join POST both carry verify=True
    assert all(c.kwargs.get("verify") is True for c in wired.get.call_args_list)
    assert wired.post.call_args.kwargs["verify"] is True
