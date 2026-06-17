# openbao_autounseal

> **Fork notes (VizzleTF).** Fork of [pyToshka/vault-autounseal](https://github.com/pyToshka/vault-autounseal),
> rebranded to **openbao-autounseal** for [OpenBao](https://openbao.org) HA on
> Kubernetes (project name, image, Helm chart and env-var prefix all changed
> `VAULT_*` → `OPENBAO_*`).
>
> **Why this fork exists.** After a full reboot of all control-plane nodes, an
> OpenBao HA StatefulSet (`podManagementPolicy: OrderedReady`, Shamir seal) came
> up sealed and the only upstream-released image (`opennix/vault-autounseal:vault-autounseal-0.5.2`)
> never discovered it — `Discovered Vault instance(s): []` forever — leaving the
> whole cluster's ExternalSecrets down. Two bugs in that released image:
> 1. the pod label selector was hardcoded to `vault-sealed=true`, but the OpenBao
>    Helm chart labels pods `openbao-sealed=true`;
> 2. the pod list was fetched **once** before the scan loop, so a pod that
>    appeared later (or had no IP yet) was never seen.
>
> Both bugs are already fixed on upstream `main` (label selector made
> env-configurable; pod list re-fetched every scan cycle — upstream PR #41), but
> upstream only shipped those fixes via floating `latest`/`main` tags, never a
> pinnable release image past `0.5.2`.
>
> **What this fork does.** Beyond the rebrand, no upstream *logic* change was
> needed — `main` already carries the fix. The fork re-points CI to publish a
> **pinnable, multi-arch image to GitHub Container Registry**:
> `ghcr.io/vizzletf/openbao-autounseal`, and renames the config env prefix to
> `OPENBAO_*`. Consume it with
> `OPENBAO_LABEL_SELECTOR=app.kubernetes.io/instance=openbao,component=server`.

## Disclaimer
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## What for

As you know, OpenBao provides several mechanisms for auto unsealing. However, sometimes I couldn't use AWS or GCP as the cloud provider. The main idea was to use Kubernetes secrets as the source for auto unsealing.

## Tested on

| Engine     | Version       | OpenBao mode |
|------------|---------------|------------|
| kind       | v1.29.1       | single/ha  |
| crc        | 2.32.0+54a6f9 | single     |
| OpenShift  | 4.14.8        | single/ha  |
| Kubernetes | v1.29.1       | single/ha  |
|            |               |            |

## Dependencies

- Kubernetes
- Python > 3.7

## How to use

Checkout source code from the repository

Install dependencies  via pip: `pip install -r requirements.txt`

Setup system environment

Run script `python app.py`

## System environments

| Name                    | Description                                                                                                                                     |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| OPENBAO_URL               | OpenBao server url with port e.g http://127.0.0.1:8200                                                                                            |
| OPENBAO_SECRET_SHARES     | Specifies the number of shares that should be encrypted by the HSM and stored for auto-unsealing. Currently must be the same as `secret_shares` |
| OPENBAO_SECRET_THRESHOLD  | Specifies the number of shares required to reconstruct the recovery key. This must be less than or equal to `recovery_shares`.                  |
| NAMESPACE               | Kubernetes namespace for storing openbao root key and keys                                                                                        |
| OPENBAO_ROOT_TOKEN_SECRET | Kubernetes secret name for root token                                                                                                           |
| OPENBAO_KEYS_SECRET       | Kubernetes secret name for openbao key                                                                                                            |

## Deployment

The solution can be run as docker container or inside Kubernetes

Building docker container

```shell
docker build . -t openbao-autounseal:latest

```
or build multiarch docker image:

```shell
make docker
```

or You can pull existing image from DockerHub

```shell
docker pull ghcr.io/vizzletf/openbao-autounseal
```

### Using helm chart

[Helm](https://helm.sh) must be installed to use the charts.  Please refer to
Helm's [documentation](https://helm.sh/docs) to get started.

Once Helm has been set up correctly, add the repo as follows:

  helm repo add openbao-autounseal https://pytoshka.github.io/openbao-autounseal

If you had already added this repo earlier, run `helm repo update` to retrieve
the latest versions of the packages.  You can then run `helm search repo
openbao-autounseal` to see the charts.

To install the openbao-autounseal chart:

    helm install openbao-autounseal openbao-autounseal/openbao-autounseal --set=settings.openbao_url=http://openbao.openbao:8200

To uninstall the chart:

    helm delete openbao-autounseal

<a href="https://www.buymeacoffee.com/pyToshka" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
