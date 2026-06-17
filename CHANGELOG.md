# Changelog

This is a fork of [pyToshka/vault-autounseal](https://github.com/pyToshka/vault-autounseal),
rebranded to openbao-autounseal and adapted for OpenBao. It split off from the
upstream 0.5.2 release. Upstream had already fixed the pod discovery on its
`main` branch but never shipped a release image past 0.5.2, so the fork exists
to publish a pinnable, OpenBao-native build.

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
