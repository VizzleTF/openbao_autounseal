.PHONY: help
help: ## Help for usage
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
all: docker
docker: ## Build docker image for local usage
	docker buildx build -t openbao-autounseal:local --platform linux/arm64,linux/amd64 .

helm_template:  ## Locally render templates for chart
	helm template -n openbao-autounseal openbao-autounseal charts/openbao-autounseal --set=settings.openbao_url=http://openbao.openbao:8200

helm_install: ## Install OpenBao auto-unseal helm chart
	helm upgrade --install --create-namespace -n openbao-autounseal openbao-autounseal charts/openbao-autounseal --set=settings.openbao_url=http://openbao.openbao:8200
	kubectl rollout restart deployment openbao-autounseal -n openbao-autounseal

helm_install_openbao:  ## Install OpenBao chart
	helm repo add openbao https://openbao.github.io/openbao-helm
	helm repo update
	helm install --create-namespace -n openbao openbao openbao/openbao

get_root_token: ## Get OpenBao root token
	kubectl get secret -n openbao-autounseal openbao-root-token  -o json | jq -r '.data.root_token' | base64 -d

kind_m1: ## Run kind kubernetes cluster ARM
	DOCKER_DEFAULT_PLATFORM='linux/arm64' kind create cluster --config tests/kind.yml

kind: ## Run kind kubernetes cluster X86
	kind create cluster --config tests/kind.yml

deploy_local_m1: kind_m1 ## Deploy auto-unseal to kind ARM, OpenBao ha mode disabled
	helm install --create-namespace -n openbao openbao openbao/openbao
	helm upgrade --install --create-namespace -n openbao-autounseal  --set=settings.openbao_url=http://openbao.openbao:8200 openbao-autounseal charts/openbao-autounseal/

deploy_local_kind: kind ## Deploy auto-unseal to kind x86, OpenBao ha mode disabled
	helm upgrade --install --create-namespace -n openbao openbao openbao/openbao
	helm upgrade --install --create-namespace -n openbao-autounseal  --set=settings.openbao_url=http://openbao.openbao:8200 openbao-autounseal charts/openbao-autounseal/

delete_local_kind: ## Delete kind cluster
	kind delete cluster -n openbao

run_local_crc_single: ## Deploy to RedHat CRC OpenBao single
	helm upgrade --install --create-namespace -n openbao openbao openbao/openbao --set "global.openshift=true"
	helm upgrade --install --create-namespace -n openbao-autounseal  --set=settings.openbao_url=http://openbao.openbao:8200 openbao-autounseal charts/openbao-autounseal/

run_local_ha: ## Deploy helm charts to current context OpenBao Ha Mode
	helm upgrade --install --create-namespace -n openbao openbao openbao/openbao --set "global.openshift=true" --set="server.ha.enabled=true" --set="server.ha.raft.enabled=true"
	helm upgrade --install --create-namespace -n openbao-autounseal  --set=settings.openbao_url=http://openbao.openbao:8200 openbao-autounseal charts/openbao-autounseal/

uninstall_chart: ## Uninstall helm charts from current context
	helm uninstall  -n openbao openbao || true
	helm uninstall  -n openbao-autounseal openbao-autounseal || true
	kubectl delete ns openbao || true
	kubectl delete ns openbao-autounseal || true
