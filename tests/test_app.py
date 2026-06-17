"""Unit tests for the OpenBao auto-unseal controller.

Exercises every helper and the refactored entrypoint (configure / scan_cycle /
main) with a mocked ``requests`` and Kubernetes client, so no live cluster is
needed. The functions read module-level globals that ``configure`` sets at
startup; the ``wired`` fixture injects test doubles for them.
"""
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock

import kubernetes
import pytest
import requests as real_requests

import app


def _pod(name, ip):
    return SimpleNamespace(metadata=SimpleNamespace(name=name), status=SimpleNamespace(pod_ip=ip))


# --------------------------------------------------------------------------- #
# resolve_tls_verify / list_convert / tracing_formatter
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


def test_tracing_formatter_builds_format_and_extras():
    record = {"extra": {}}
    out = app.tracing_formatter(record)
    assert "{message}" in out
    assert "stack" in record["extra"] and "timestamp" in record["extra"]


# --------------------------------------------------------------------------- #
# get_kubernetes_client
# --------------------------------------------------------------------------- #
def test_get_kubernetes_client_incluster(monkeypatch):
    cfg, cli = MagicMock(), MagicMock()
    monkeypatch.setattr(app, "config", cfg)
    monkeypatch.setattr(app, "client", cli)
    assert app.get_kubernetes_client() is cli
    cfg.load_incluster_config.assert_called_once()
    cfg.load_kube_config.assert_not_called()


def test_get_kubernetes_client_falls_back_to_kubeconfig(monkeypatch):
    cfg, cli = MagicMock(), MagicMock()
    cfg.load_incluster_config.side_effect = kubernetes.config.config_exception.ConfigException("no")
    monkeypatch.setattr(app, "config", cfg)
    monkeypatch.setattr(app, "client", cli)
    assert app.get_kubernetes_client() is cli
    cfg.load_kube_config.assert_called_once()


# --------------------------------------------------------------------------- #
# Shared wiring for functions that touch module globals
# --------------------------------------------------------------------------- #
@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(app, "TLS_VERIFY", True, raising=False)
    monkeypatch.setattr(app, "auto_unseal_payload", {"secret_shares": 1, "secret_threshold": 1}, raising=False)
    monkeypatch.setattr(app, "status_init", 0, raising=False)
    monkeypatch.setattr(app, "status_unseal", 1, raising=False)
    monkeypatch.setattr(app, "status_ok", 2, raising=False)
    monkeypatch.setattr(app, "status_error", 3, raising=False)
    monkeypatch.setattr(app, "pod_retrieval_max_retries", 2, raising=False)
    monkeypatch.setattr(app, "scan_delay", 0, raising=False)
    monkeypatch.setattr(app, "namespace", "openbao", raising=False)
    monkeypatch.setattr(app, "root_token", "openbao-root-token", raising=False)
    monkeypatch.setattr(app, "openbao_keys", "openbao-keys", raising=False)
    monkeypatch.setattr(app, "openbao_label_selector", "openbao-sealed=true", raising=False)
    monkeypatch.setattr(app, "url", SimpleNamespace(scheme="https", hostname="h", port=8200), raising=False)
    monkeypatch.setattr(app, "openbao_port", 8200, raising=False)
    monkeypatch.setattr(app, "sleep", lambda *_a, **_k: None)
    fake = MagicMock()
    fake.exceptions = real_requests.exceptions
    monkeypatch.setattr(app, "requests", fake)
    return fake


# --------------------------------------------------------------------------- #
# init_openbao / openbao_unseal
# --------------------------------------------------------------------------- #
def test_init_openbao_passes_verify(wired):
    wired.put.return_value.json.return_value = {"root_token": "t", "keys": ["k"]}
    assert app.init_openbao("https://bao:8200") == {"root_token": "t", "keys": ["k"]}
    assert wired.put.call_args.kwargs["verify"] is True


def test_init_openbao_connection_error_returns_none(wired):
    wired.put.side_effect = real_requests.exceptions.ConnectionError("down")
    assert app.init_openbao("https://bao:8200") is None


def test_openbao_unseal_passes_verify(wired):
    app.openbao_unseal("unseal-key", "https://bao:8200")
    assert wired.put.call_args.kwargs["verify"] is True


def test_openbao_unseal_logs_request_error(wired):
    wired.put.side_effect = real_requests.exceptions.RequestException("boom")
    app.openbao_unseal("k", "https://bao:8200")  # swallowed, no raise


# --------------------------------------------------------------------------- #
# create_secrets / read_secret / delete_secret
# --------------------------------------------------------------------------- #
def test_create_secrets_success(wired, monkeypatch):
    monkeypatch.setattr(app, "client", MagicMock(), raising=False)
    monkeypatch.setattr(app, "k8s_secret", MagicMock(), raising=False)
    api = MagicMock()
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    app.create_secrets({"root_token": "t", "keys": ["k0", "k1"]})
    assert api.create_namespaced_secret.call_count == 2


def test_create_secrets_handles_api_exception(wired, monkeypatch):
    monkeypatch.setattr(app, "client", MagicMock(), raising=False)
    monkeypatch.setattr(app, "k8s_secret", MagicMock(), raising=False)
    api = MagicMock()
    api.create_namespaced_secret.side_effect = kubernetes.client.exceptions.ApiException("nope")
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    app.create_secrets({"root_token": "t", "keys": ["k0"]})  # logged, no raise


def test_read_secret_decodes_and_unseals(wired, monkeypatch):
    api = MagicMock()
    api.read_namespaced_secret.return_value.data = {"0": base64.b64encode(b"unsealkey").decode()}
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    unseal = MagicMock()
    monkeypatch.setattr(app, "openbao_unseal", unseal)
    app.read_secret("openbao-keys", "https://bao:8200")
    unseal.assert_called_once_with("unsealkey", "https://bao:8200")


def test_delete_secret_logs_each(wired, monkeypatch):
    api = MagicMock()
    api.delete_namespaced_secret.return_value = SimpleNamespace(details=SimpleNamespace(name="x"))
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    app.delete_secret(["a", "b"])
    assert api.delete_namespaced_secret.call_count == 2


# --------------------------------------------------------------------------- #
# get_seal_status — every branch
# --------------------------------------------------------------------------- #
def test_get_seal_status_ok_path(wired):
    wired.get.return_value.json.return_value = {"initialized": True, "sealed": False}
    assert app.get_seal_status("https://bao:8200", True) == app.status_ok
    assert wired.get.call_args.kwargs["verify"] is True


def test_get_seal_status_already_initialized_quorum(wired):
    wired.get.return_value.json.return_value = {"initialized": False}
    assert app.get_seal_status("https://bao:8200", True) == app.status_init


def test_get_seal_status_init_and_unseal(wired, monkeypatch):
    wired.get.return_value.json.return_value = {"initialized": False}
    monkeypatch.setattr(app, "delete_secret", MagicMock())
    monkeypatch.setattr(app, "init_openbao", MagicMock(return_value={"root_token": "t", "keys": ["k"]}))
    monkeypatch.setattr(app, "create_secrets", MagicMock())
    monkeypatch.setattr(app, "read_secret", MagicMock())
    assert app.get_seal_status("https://bao:8200", False) == app.status_init


def test_get_seal_status_init_failure_returns_error(wired, monkeypatch):
    wired.get.return_value.json.return_value = {"initialized": False}
    monkeypatch.setattr(app, "delete_secret", MagicMock(
        side_effect=kubernetes.client.exceptions.ApiException("x")))
    monkeypatch.setattr(app, "init_openbao", MagicMock(return_value=None))
    assert app.get_seal_status("https://bao:8200", False) == app.status_error


def test_get_seal_status_sealed_unseals(wired, monkeypatch):
    wired.get.return_value.json.return_value = {"initialized": True, "sealed": True}
    monkeypatch.setattr(app, "read_secret", MagicMock())
    assert app.get_seal_status("https://bao:8200", True) == app.status_unseal


def test_get_seal_status_connection_error(wired):
    wired.get.side_effect = real_requests.exceptions.ConnectionError("down")
    assert app.get_seal_status("https://bao:8200", True) == app.status_error


# --------------------------------------------------------------------------- #
# get_quorum_established / wait_for_quorum
# --------------------------------------------------------------------------- #
def test_get_quorum_established_acknowledged(wired):
    wired.get.return_value.json.return_value = {"leader_address": "https://m:8200"}
    app.get_quorum_established(False, ["https://m:8200", "https://r:8200"], "https://m:8200")
    assert wired.get.call_args.kwargs["verify"] is True


def test_get_quorum_established_not_acknowledged(wired):
    wired.get.return_value.json.return_value = {"leader_address": "https://other:8200"}
    app.get_quorum_established(False, ["https://m:8200", "https://r:8200"], "https://m:8200")


def test_get_quorum_established_node_not_ready(wired):
    wired.get.return_value.json.return_value = {}  # no leader_address
    app.get_quorum_established(False, ["https://m:8200", "https://r:8200"], "https://m:8200")


def test_wait_for_quorum_joins_and_verifies(wired, monkeypatch):
    wired.get.return_value.json.return_value = {"leader_address": "https://m:8200"}
    wired.get.return_value.status_code = 200
    monkeypatch.setattr(app, "read_secret", MagicMock())
    app.wait_for_quorum(["https://m:8200", "https://r:8200"], "https://m:8200")
    assert wired.post.call_args.kwargs["verify"] is True


def test_wait_for_quorum_join_connection_error(wired, monkeypatch):
    wired.get.return_value.json.return_value = {"leader_address": "https://m:8200"}
    wired.post.side_effect = real_requests.exceptions.ConnectionError("down")
    monkeypatch.setattr(app, "read_secret", MagicMock())
    assert app.wait_for_quorum(["https://m:8200", "https://r:8200"], "https://m:8200") == app.status_error


# --------------------------------------------------------------------------- #
# get_openbao_pods
# --------------------------------------------------------------------------- #
def test_get_openbao_pods_empty(wired, monkeypatch):
    api = MagicMock()
    api.list_namespaced_pod.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    assert app.get_openbao_pods().items == []


def test_get_openbao_pods_ready(wired, monkeypatch):
    api = MagicMock()
    api.list_namespaced_pod.return_value = SimpleNamespace(items=[_pod("p0", "10.0.0.1")])
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    assert len(app.get_openbao_pods().items) == 1


def test_get_openbao_pods_no_ip_then_exhausted(wired, monkeypatch):
    api = MagicMock()
    api.list_namespaced_pod.return_value = SimpleNamespace(items=[_pod("p0", None)])
    monkeypatch.setattr(app, "api_instance", api, raising=False)
    result = app.get_openbao_pods()
    assert api.list_namespaced_pod.call_count == app.pod_retrieval_max_retries
    assert result.items[0].status.pod_ip is None


# --------------------------------------------------------------------------- #
# configure
# --------------------------------------------------------------------------- #
_REQUIRED_ENV = {
    "OPENBAO_URL": "https://openbao.openbao:8200",
    "OPENBAO_SECRET_SHARES": "3",
    "OPENBAO_SECRET_THRESHOLD": "3",
    "NAMESPACE": "openbao",
    "OPENBAO_ROOT_TOKEN_SECRET": "root",
    "OPENBAO_KEYS_SECRET": "keys",
    "OPENBAO_SCAN_DELAY": "5",
}


def test_configure_missing_env_exits(monkeypatch):
    for k in _REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit) as e:
        app.configure()
    assert e.value.code == 2


def test_configure_bad_retries_exits(monkeypatch):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("OPENBAO_POD_RETRIEVAL_MAX_RETRIES", "0")
    monkeypatch.setattr(app, "get_kubernetes_client", MagicMock())
    with pytest.raises(SystemExit) as e:
        app.configure()
    assert e.value.code == 2


def test_configure_happy_path(monkeypatch):
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("OPENBAO_POD_RETRIEVAL_MAX_RETRIES", raising=False)
    monkeypatch.setattr(app, "get_kubernetes_client", MagicMock())
    app.configure()
    assert app.namespace == "openbao"
    assert app.scan_delay == 5
    assert app.auto_unseal_payload == {"secret_shares": 3, "secret_threshold": 3}
    assert app.url.scheme == "https"


# --------------------------------------------------------------------------- #
# scan_cycle / main
# --------------------------------------------------------------------------- #
def test_scan_cycle_single_node_init(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        return_value=SimpleNamespace(items=[_pod("p0", "10.0.0.1")])))
    monkeypatch.setattr(app, "get_seal_status", MagicMock(return_value=app.status_init))
    wfq = MagicMock()
    monkeypatch.setattr(app, "wait_for_quorum", wfq)
    initialized, leader = app.scan_cycle(False, "")
    assert initialized is True and leader == "https://10.0.0.1:8200"
    wfq.assert_called_once()


def test_scan_cycle_ha_unseal(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        return_value=SimpleNamespace(items=[_pod("p0", "10.0.0.1"), _pod("p1", "10.0.0.2")])))
    monkeypatch.setattr(app, "get_seal_status", MagicMock(return_value=app.status_init))
    monkeypatch.setattr(app, "wait_for_quorum", MagicMock())
    initialized, leader = app.scan_cycle(False, "")
    assert initialized is True


def test_scan_cycle_unseal_status(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        return_value=SimpleNamespace(items=[_pod("p0", "10.0.0.1")])))
    monkeypatch.setattr(app, "get_seal_status", MagicMock(return_value=app.status_unseal))
    initialized, _ = app.scan_cycle(True, "https://10.0.0.1:8200")
    assert initialized is True


def test_scan_cycle_heartbeat_failure(wired, monkeypatch):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", "/nonexistent-dir/hb")
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        return_value=SimpleNamespace(items=[])))
    initialized, leader = app.scan_cycle(False, "")
    assert initialized is False  # heartbeat OSError swallowed, empty discovery


def test_scan_cycle_request_exception(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        side_effect=real_requests.exceptions.RequestException("boom")))
    assert app.scan_cycle(False, "") == (False, "")


def test_scan_cycle_api_exception(wired, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "HEARTBEAT_FILE", str(tmp_path / "hb"))
    monkeypatch.setattr(app, "get_openbao_pods", MagicMock(
        side_effect=kubernetes.client.exceptions.ApiException("api")))
    assert app.scan_cycle(False, "") == (False, "")


def test_main_runs_one_cycle_then_breaks(monkeypatch):
    monkeypatch.setattr(app, "configure", MagicMock())
    monkeypatch.setattr(app, "scan_cycle", MagicMock(return_value=(True, "https://m:8200")))
    monkeypatch.setattr(app, "scan_delay", 0, raising=False)

    class _Stop(Exception):
        pass

    def _sleep(*_a, **_k):
        raise _Stop()

    monkeypatch.setattr(app, "sleep", _sleep)
    with pytest.raises(_Stop):
        app.main()
    app.configure.assert_called_once()
    app.scan_cycle.assert_called_once_with(False, "")
