# openbao-autounseal

Initialises OpenBao on first start and unseals its pods from Kubernetes Secrets.
The controller polls the OpenBao pods matched by `settings.openbao_label_selector`.
On first start it calls `/sys/init` and stores the unseal keys and root token in
two Secrets in the release namespace. After that it unseals every sealed pod via
`/sys/unseal`.

## Install

```shell
helm repo add openbao-autounseal https://vizzletf.github.io/openbao_autounseal
helm install openbao-autounseal openbao-autounseal/openbao-autounseal \
  --namespace openbao \
  --set settings.openbao_url=http://openbao.openbao:8200
```

`settings.openbao_url` defaults to `https://` since 0.5.13. If your OpenBao
listener does not terminate TLS, set an `http://` URL as above.

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `settings.openbao_url` | `https://openbao.openbao:8200` | OpenBao API URL; required |
| `settings.openbao_secret_shares` | `3` | Key shares created at init |
| `settings.openbao_secret_threshold` | `3` | Shares needed to unseal |
| `settings.openbao_root_token_secret` | `openbao-root-token` | Secret that receives the root token |
| `settings.openbao_keys_secret` | `openbao-keys` | Secret that receives the unseal keys |
| `settings.scan_delay` | `5` | Seconds between scans |
| `settings.openbao_label_selector` | `app.kubernetes.io/instance=openbao,component=server` | Selects the OpenBao pods |
| `settings.log_level` | `INFO` | Loguru log level |
| `image.repository` | `ghcr.io/vizzletf/openbao-autounseal` | Image repository |
| `image.tag` | chart `appVersion` | Image tag |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy |
| `resources` | 25m/64Mi requests, 100m/128Mi limits | Container resources |
| `serviceAccount.create` | `true` | Create the ServiceAccount bound to the Role |
| `serviceAccount.name` | generated | ServiceAccount name |
| `serviceAccount.annotations` | `{}` | ServiceAccount annotations |
| `livenessProbe.enabled` | `true` | Restart the pod when the scan loop stalls |
| `livenessProbe.staleSeconds` | `90` | Heartbeat age that fails the probe; keep it well above `scan_delay` |

`values.schema.json` rejects unknown top-level keys. `global` and
`homelab-common` are allowed so the chart can share a values file with an
umbrella chart.
