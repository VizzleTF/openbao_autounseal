# Changelog

This is a fork of [pyToshka/vault-autounseal](https://github.com/pyToshka/vault-autounseal),
rebranded to openbao-autounseal and adapted for OpenBao. It split off from the
upstream 0.5.2 release. Upstream had already fixed the pod discovery on its
`main` branch but never shipped a release image past 0.5.2, so the fork exists
to publish a pinnable, OpenBao-native build.

## 0.5.11

Cleanups from a second review pass. The quorum and unseal log lines now name the
node they're acting on instead of a stale module-global, so the logs match
reality during HA operations. Startup uses sys.exit (the bare exit builtin isn't
guaranteed outside the site module), and the configmap quotes its string values.

## 0.5.10

Startup validates the required env vars and exits with a clear message if one is
missing, instead of crashing deep in the loop with a TypeError. Pod discovery
takes the namespace from the NAMESPACE env rather than splitting it out of the
service URL, which broke on a bare hostname or an external address. Also bounded
the quorum-wait loop so a stuck node can't spin it forever, made the generated
secret keys strings, and stopped a failed init from crashing the unseal path.
Added a liveness probe: the app touches /tmp/heartbeat each cycle and the probe
restarts the pod if it goes stale, so a wedged loop recovers on its own.

## 0.5.9

Cut RBAC down to a namespaced Role with only the verbs the controller actually
calls (list pods; get/create/delete secrets), replacing a cluster-wide
ClusterRole that granted full CRUD on secrets everywhere. The pod also runs with
a restricted securityContext by default: non-root (uid 65532), read-only root
filesystem, all capabilities dropped, seccomp RuntimeDefault.

## 0.5.8

The scan loop now catches request and Kubernetes API errors and retries on the
next cycle instead of letting them kill the process. 0.5.7 recovered from a
vanished pod only by timing out and letting Kubernetes restart the container;
now it recovers in place with no restart. Dependencies bumped to current
versions with no known CVEs (pip-audit clean): kubernetes 36, requests 2.34.2,
urllib3 2.7.0, certifi 2026.6.17, loguru 0.7.3.

## 0.5.7

Added a connect/read timeout to every OpenBao HTTP call (init, unseal,
seal-status, leader, raft join). Before this, when a pod the controller had
already discovered went away (deleted or rescheduled), the next request to its
old IP blocked forever and the scan loop froze. The container stayed Ready,
logging stopped, and nothing got unsealed until someone restarted it. I found
it by deleting a standby OpenBao pod and watching it sit sealed.

## 0.5.6

Pinned Python to 3.13 on both the build and the runtime. The build stage
installs packages into a version-specific `site-packages` path, and the runtime
base had drifted to a newer Python than the build stage, so imports failed
before the logger even started and the container crash-looped with empty logs.
The build now uses `python:3.13-slim` and the runtime is
`gcr.io/distroless/python3-debian13`, which keeps Python at 3.13 instead of
following the floating `python3` tag.

Also set the chart defaults for OpenBao: unseal threshold 3, `openbao_url`
pointing at the in-cluster service, the `openbao-keys` and `openbao-root-token`
secret names, and the `app.kubernetes.io/instance=openbao,component=server` pod
selector. The image defaults to the chart appVersion.

## Fork setup (from 0.5.2)

Renamed everything from vault-autounseal to openbao-autounseal: the Helm chart,
the image, and the config env prefix (`VAULT_*` became `OPENBAO_*`). The
Makefile test target installs OpenBao now instead of HashiCorp Vault.

CI publishes a multi-arch image to `ghcr.io/vizzletf/openbao-autounseal` with
the built-in GitHub token, and the chart goes to the GitHub Pages Helm repo at
https://vizzletf.github.io/openbao_autounseal. The application code is unchanged
from upstream `main`, which already made the pod label selector configurable and
re-listed pods on every scan cycle (upstream PR #41).

### Withdrawn

0.5.4 and 0.5.5 were tagged during the Python work and then pulled. 0.5.4 had
the build/runtime Python mismatch. 0.5.5 pinned Python 3.11 on Debian 12, which
worked, but 0.5.6 moved to 3.13. Use 0.5.6 or later.
