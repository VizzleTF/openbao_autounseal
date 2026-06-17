#!/usr/bin/env python3
import base64
import json
import os
import sys
import traceback
import datetime
from itertools import takewhile
from time import sleep
from urllib.parse import urlparse

import kubernetes
import requests
from kubernetes import client, config
from loguru import logger
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# (connect, read) timeout for every OpenBao HTTP call. Without it a discovered
# pod that disappears (deleted/rescheduled) makes requests block forever and the
# scan loop hangs silently — the pod stays Ready but never unseals anything.
REQUEST_TIMEOUT = (5, 30)


def get_kubernetes_client():
    try:
        config.load_incluster_config()
        client.configuration.assert_hostname = False
    except kubernetes.config.config_exception.ConfigException:
        config.load_kube_config()
        client.configuration.assert_hostname = False
    return client


def tracing_formatter(record):
    def function(f):
        return "/loguru/" not in f.filename

    frames = takewhile(function, traceback.extract_stack())
    stack = " > ".join("{}:{}:{}".format(f.filename, f.name, f.lineno) for f in frames)
    record["extra"]["stack"] = stack
    record["extra"]["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    return "{level} | {extra[timestamp]} {extra[stack]} - {message}\n{exception}"


def list_convert(lst):
    converted_dict = {i: lst[i] for i in range(0, len(lst))}
    return converted_dict


def init_openbao(openbao_instance_url):
    try:
        logger.info(f"Initializing OpenBao at {openbao_instance_url}")
        init_openbao_request = requests.put(
            f"{openbao_instance_url}/v1/sys/init",
            data=json.dumps(auto_unseal_payload),
            verify=False,  # nosec
            timeout=REQUEST_TIMEOUT,
        )
        response = init_openbao_request.json()
        return response
    except requests.exceptions.ConnectionError as init_openbao_error:
        logger.info(
            "Got ConnectionError for  {}. Please check OpenBao api url/port",
            init_openbao_error,
        )


def create_secrets(secret):
    k8s_secret.metadata = client.V1ObjectMeta(name=root_token)
    k8s_secret.type = "Opaque"
    k8s_secret.string_data = {"root_token": secret["root_token"]}
    try:
        api_instance.create_namespaced_secret(namespace=namespace, body=k8s_secret)
    except kubernetes.client.exceptions.ApiException as create_secret_error:
        logger.error("Error during creation on OpenBao secret {}", create_secret_error)

    k8s_secret.metadata = client.V1ObjectMeta(name=openbao_keys)
    k8s_secret.type = "Opaque"
    k8s_secret.string_data = list_convert(secret["keys"])
    try:
        api_instance.create_namespaced_secret(namespace=namespace, body=k8s_secret)
    except kubernetes.client.exceptions.ApiException as create_secret_error:
        logger.error("Error during creation on OpenBao secret {}", create_secret_error)


def read_secret(name, openbao_instance_url):
    secret_client = api_instance.read_namespaced_secret(
        name=name, namespace=namespace
    ).data
    for secret in secret_client.values():
        key = base64.b64decode(secret)
        openbao_unseal(key.decode(), openbao_instance_url)


def get_secret(name):
    secret = api_instance.read_namespaced_secret(name=name, namespace=namespace).data
    if secret:
        return True


def openbao_unseal(key, openbao_instance_url):
    payload = {"key": key}
    try:
        requests.put(
            f"{openbao_instance_url}/v1/sys/unseal",
            data=json.dumps(payload),
            verify=False,  # nosec
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError as unseal_error:
        logger.error("During unseal got error", unseal_error)
    if key is None:
        logger.info("Unseal key not found")
    else:
        logger.info("{} has been provided an unseal key", openbao_instance_url)


def get_seal_status(openbao_instance_url, openbao_status):
    try:
        get_seal = requests.get(
            f"{openbao_instance_url}/v1/sys/seal-status",
            verify=False,  # nosec
            timeout=REQUEST_TIMEOUT,
        )
        if not get_seal.json()["initialized"]:
            if openbao_status:
                logger.info(
                    "OpenBao has already been initialized, establishing quorum instead"
                )
                return status_init  # Return status_init to establish quorum

            logger.info("Going to init and unseal OpenBao")
            try:
                delete_secret([root_token, openbao_keys])
            except kubernetes.client.exceptions.ApiException as delete_secret_error:
                logger.error(
                    "During  initialize got a error -> {}", delete_secret_error
                )
            create_secrets(init_openbao(openbao_instance_url))

            logger.info("Unsealing OpenBao node {}", replica_url)
            read_secret(openbao_keys, openbao_instance_url)

            return status_init
        if get_seal.json()["sealed"]:
            logger.info("Unsealing OpenBao node {}", replica_url)
            read_secret(openbao_keys, openbao_instance_url)

            return status_unseal
    except requests.exceptions.ConnectionError as seal_status_error:
        logger.info("Unexpected status -> {}", seal_status_error)
        return status_error

    return status_ok


def delete_secret(secret_name):
    for secret in secret_name:
        secret_for_delete = api_instance.delete_namespaced_secret(
            name=secret, namespace=namespace
        )
        logger.info("Secret {} has been deleted", secret_for_delete.details.name)


def get_quorum_established(quorum_established, replica_list, main_url):
    while not quorum_established:
        quorum_established = True
        for openbao_instance_url in replica_list:
            if openbao_instance_url == main_url:
                continue

            leader_status = requests.get(
                f"{openbao_instance_url}/v1/sys/leader",
                verify=False,  # nosec
                timeout=REQUEST_TIMEOUT,
            )

            if "leader_address" not in leader_status.json():
                quorum_established = False
                logger.info(
                    "OpenBao node {} is not ready: {} ", replica_url, leader_status.json()
                )
                continue
            if leader_status.json()["leader_address"] == main_url:
                logger.info(
                    "OpenBao node {} has acknowledged {} as the leader",
                    openbao_instance_url,
                    main_url,
                )
            else:
                logger.info(
                    "OpenBao node {} has not acknowledged {} as the leader",
                    openbao_instance_url,
                    main_url,
                )

                quorum_established = False
                break

        sleep(5)


def wait_for_quorum(replica_list, main_url):
    payload = {"leader_api_addr": main_url}
    leader_status = requests.get(
        f"{main_url}/v1/sys/leader", verify=False, timeout=REQUEST_TIMEOUT  # nosec
    )
    logger.info(
        "Leader http code {}, response json {}",
        leader_status.status_code,
        leader_status.json(),
    )
    for openbao_instance_url in replica_list:
        if openbao_instance_url == main_url:
            continue
        try:
            logger.info("Joining {} to leader", openbao_instance_url)

            requests.post(
                f"{openbao_instance_url}/v1/sys/storage/raft/join",
                data=json.dumps(payload),
                verify=False,  # nosec
                timeout=REQUEST_TIMEOUT,
            )

        except requests.exceptions.ConnectionError as connection_error:
            logger.info("Unexpected error {}", connection_error)
            return status_error

        logger.info("Unsealing {}", replica_url)
        read_secret(openbao_keys, openbao_instance_url)

    quorum_established = False

    get_quorum_established(
        quorum_established=quorum_established,
        replica_list=replica_list,
        main_url=main_url,
    )

    logger.info("Quorum has been established with {} as the leader", main_url)


def get_openbao_pods():
    if pod_retrieval_max_retries <= 0:
        logger.error("Pod retrieval max retries cannot be lower than 1: {}", pod_retrieval_max_retries)
        exit(2)

    tries = 0
    pod_list = None
    while tries < pod_retrieval_max_retries:
        tries = tries + 1
        pod_list = api_instance.list_namespaced_pod(
            namespace=openbao_namespace, label_selector=openbao_label_selector
        )

        if len(pod_list.items) == 0:
            # No pods yet (e.g. cold cluster start). Don't exit — let the caller
            # log an empty discovery and retry on the next scan cycle.
            logger.warning("No OpenBao pods match selector {} yet", openbao_label_selector)
            return pod_list

        openbao_pods_with_no_ip = [pod.metadata.name for pod in pod_list.items if pod.status.pod_ip is None]

        if len(openbao_pods_with_no_ip) > 0:
            logger.warning("OpenBao pods have no assigned IP address yet: {}", openbao_pods_with_no_ip)
            sleep(scan_delay)
            continue

        return pod_list

    # Retries exhausted: return what we have. The scan loop skips pods without an
    # IP, so a slow-to-schedule replica just gets picked up on a later cycle
    # instead of crashing the controller.
    logger.warning("Some OpenBao pods still have no IP; proceeding with the ready ones")
    return pod_list


if __name__ == "__main__":

    openbao_initialized = False
    leader_url = ""
    secret_shares = ""  # nosec
    secret_threshold = ""  # nosec
    namespace = ""
    root_token = ""  # nosec
    openbao_keys = ""  # nosec
    scan_delay = ""
    openbao_url = ""
    pod_retrieval_max_retries = ""
    try:
        openbao_url = os.environ["OPENBAO_URL"]
        secret_shares = os.environ["OPENBAO_SECRET_SHARES"]
        secret_threshold = os.environ["OPENBAO_SECRET_THRESHOLD"]
        namespace = os.environ["NAMESPACE"]
        root_token = os.environ["OPENBAO_ROOT_TOKEN_SECRET"]
        openbao_keys = os.environ["OPENBAO_KEYS_SECRET"]
        scan_delay = int(os.environ["OPENBAO_SCAN_DELAY"])
        pod_retrieval_max_retries = int(os.environ.get("OPENBAO_POD_RETRIEVAL_MAX_RETRIES", 5))
        openbao_label_selector = os.environ.get("OPENBAO_LABEL_SELECTOR", "openbao-sealed=true")
        if not openbao_url:
            raise KeyError
    except KeyError as error:
        if not secret_shares:
            secret_shares = 5
        if not namespace:
            namespace = "default"
        if not root_token:
            root_token = "root-token"  # nosec
        if not openbao_keys:
            openbao_keys = "openbao-keys"
        if not secret_threshold:
            secret_threshold = 5
        if not scan_delay:
            scan_delay = 5
        else:
            print("Please check system variable {}", error)
            exit(2)
    logger.remove()
    logger.add(sys.stderr, format=tracing_formatter)
    logger.info("Start OpenBao auto unseal")
    k8s_client = get_kubernetes_client()
    api_instance = k8s_client.CoreV1Api()
    k8s_secret = k8s_client.V1Secret()
    status_init = 0
    status_unseal = 1
    status_ok = 2
    status_error = 3
    auto_unseal_payload = {
        "secret_shares": int(secret_shares),
        "secret_threshold": int(secret_threshold),
    }

    url = urlparse(openbao_url)
    openbao_hostname = url.hostname
    openbao_port = url.port
    openbao_namespace = url.hostname.split(".")[1]
    logger.info("OpenBao Hostname: {} OpenBao Port: {}", openbao_hostname, openbao_port)

    while True:
        logger.info("Begin scan cycle")
        # Discover the current OpenBao pods (by label selector) on every cycle, so
        # a deleted/rescheduled pod with a new IP is picked up. A failed HTTP call
        # or k8s API error is logged and retried next cycle instead of killing the
        # process — a discovered pod that disappears must not wedge the loop.
        try:
            pods = get_openbao_pods()
            openbao_replicas = sorted(
                f"{url.scheme}://{pod.status.pod_ip}:{openbao_port}"
                for pod in pods.items
                if pod.status.pod_ip
            )
            logger.info("Discovered OpenBao instance(s): {}", openbao_replicas)
            for replica_url in openbao_replicas:
                status = get_seal_status(replica_url, openbao_initialized)
                if status == status_init:
                    if len(openbao_replicas) > 1:
                        logger.info(
                            "OpenBao running in High Availability mode will unseal OpenBao nodes one by one"
                        )
                    else:
                        logger.info("OpenBao running in Single Node mode will unseal")
                    # Only set the Leader URL once
                    if not openbao_initialized:
                        openbao_initialized = True
                        leader_url = replica_url
                    logger.info(
                        "OpenBao was just initialized, waiting for quorum to be established"
                    )
                    wait_for_quorum(openbao_replicas, leader_url)

                if status == status_unseal:
                    # If we've unsealed an instance, then by definition openbao has been initialized
                    openbao_initialized = True
                    logger.info("OpenBao has been unsealed")
        except requests.exceptions.RequestException as err:
            logger.warning("OpenBao request failed this cycle, retrying next scan: {}", err)
        except kubernetes.client.exceptions.ApiException as err:
            logger.warning("Kubernetes API error this cycle, retrying next scan: {}", err)

        sleep(scan_delay)
