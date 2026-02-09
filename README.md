# OCI Node Maintenance Handler (ONMH)

The **OCI Node Maintenance Handler** is an open-source lifecycle automation tool designed to ensure high availability for Kubernetes applications running on **Oracle Cloud Infrastructure (OCI) Container Engine for Kubernetes (OKE)**. This project provides a native OCI solution for gracefully handling **Compute Maintenance Events**. By proactively draining nodes before maintenance begins and automatically reintegrating them once completed, ONMH minimizes application downtime and manual operational overhead.

---

## How It Works

The handler operates as a serverless-to-cluster workflow:

1.  **Capture:** An [OCI Event Service](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm) rule identifies `com.oraclecloud.computeapi.maintenancerescheduled` events.
2.  **Transport:** Events are routed to an [OCI Streaming](https://(https://docs.oracle.com/en-us/iaas/Content/Streaming/Concepts/streamingoverview.htm)) queue.
3.  **Process:** A lightweight **Python-based Watchdog pod** running in your OKE cluster monitors the stream.
4.  **Schedule:** 
    *   If maintenance is in the future, the handler creates a **Kubernetes CronJob** scheduled to trigger **15 minutes** before the maintenance window.
    *   If the event is immediate (e.g. `maintenance-begin event`), it triggers an **immediate Kubernetes Job**.
5.  **Drain:** The job executes a `kubectl drain` with safety flags (`--ignore-daemonsets`, `--delete-emptydir-data`, `--force`) to migrate workloads.
6.  **Recover:** Once a `maintenance-end` event is detected, the handler automatically **uncordons** the node.

---

## Key Features

*   **Native OCI Integration:** Uses **Instance Principals** for secure, keyless authentication.
*   **Time-Aware Orchestration:** Robust ISO-8601 parsing to handle OCI-specific maintenance timestamps.
*   **Cluster-Safe RBAC:** Leverages **ClusterRoles** to manage node states without over-privileged accounts.
*   **Self-Cleaning:** Automated cleanup of completed jobs using `ttlSecondsAfterFinished`.

---

## Deployment Guide

### 1. Setup OCI Streaming
Create a Stream to act as the message bus:
1. Go to **Analytics & AI** > **Messaging** > **Streaming**.
2. Create a **Stream Pool** (Private Endpoint recommended).
3. Create a **Stream** named `node-maintenance-stream`.
4. Note the **Messages Endpoint** and **Stream OCID**.

### 2. Configure IAM Policies
Create a [dynamic group](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm) containing your OKE worker nodes:

**Dynamic Group Rule:**
```text
Any {instance.compartment.id = 'ocid1.compartment.oc1..example'}
```

Policy for the Dynamic Group:
```text
Allow dynamic-group <Group_Name> to use stream-family in compartment <Compartment_Name>
Allow dynamic-group <Group_Name> to inspect instances in compartment <Compartment_Name>
```

3. Create the OCI Event Rule
Go to **Observability & Management** > **Events Service** > **Rules**.
Create an event rule with **Condition** set to **Event Type** and **Service Name** set to **Block Volume**. Add the following filters in **Event Type**:
```text
Instance Maintenance
Instance Maintenance-begin
Instance Maintenance-end
```
Action:
Action Type: **Streaming**
Compartment: select the compartment where the stream was created
Stream: select the stream you created in [Setup OCI Streaming](https://github.com/mprestin77/oci-node-maintenance-handler/blob/master/README.md#1-setup-oci-streaming)
<img width="1219" height="657" alt="image" src="https://github.com/user-attachments/assets/e0e2357c-bba0-4386-9495-048b27d658a4" />

![image](https://github.com/mprestin77/oci-node-maintenance-handler/blob/master/images/EventRule.png)

5. Deploy to OKE
Apply the manifests:
bash
# 1. Create namespace
kubectl create namespace wd

# 2. Apply RBAC
kubectl apply -f k8s/rbac.yaml

# 3. Deploy Watchdog
kubectl apply -f k8s/deployment.yaml
Use code with caution.

Required Environment Variables:
Variable	Description
WD_STREAM_ID	The OCID of your OCI Stream.
WD_STREAM_ENDPOINT	Your Messages Endpoint URL.
PYTHONUNBUFFERED	Set to 1 for real-time logs.
🔍 Verification
Simulate an event via OCI CLI:
bash
ENCODED_VAL=$(echo '{"eventType": "com.oraclecloud.computeapi.maintenancerescheduled", "data": {"resourceId": "ocid1.instance.oc1..example"}}' | base64)
oci streaming stream message put --stream-id <OCID> --messages '[{"key": "dGVzdA==", "value": "'$ENCODED_VAL'"}]' --endpoint <Endpoint>
Use code with caution.

Check logs:
kubectl logs -f -n wd -l app=oci-node-maintenance-handler

Would you like to include a **Troubleshooting** section or the **Architecture Diagram** logic next?





## How It Workis

1.  **Capture:** An [OCI Event Service](https://docs.oracle.com) rule identifies `com.oraclecloud.computeapi.maintenancerescheduled` events.
2.  **Transport:** Events are routed to an [OCI Streaming](https://docs.oracle.com) queue.
3.  **Process:** A lightweight **Python-based Watchdog pod** running in your OKE cluster monitors the stream.
4.  **Schedule:** 
    *   If maintenance is in the future, the handler creates a **Kubernetes CronJob** scheduled to trigger **15 minutes** before the maintenance window.
    *   If the event is immediate (e.g., Preemptible/Spot termination), it triggers an **immediate Kubernetes Job**.
5.  **Drain:** The job executes a `kubectl drain` with safety flags (`--ignore-daemonsets`, `--delete-emptydir-data`, `--force`) to migrate workloads.
6.  **Recover:** Once a `maintenance-end` event is detected, the handler automatically **uncordons** the node.

## Key Features

*   **Native OCI Integration:** Uses **Instance Principals** for secure, keyless authentication.
*   **Time-Aware Orchestration:** Robust ISO-8601 parsing to handle OCI-specific maintenance timestamps.
*   **Cluster-Safe RBAC:** Leverages **ClusterRoles** to manage node states without over-privileged accounts.
*   **Self-Cleaning:** Automated cleanup of completed jobs using `ttlSecondsAfterFinished`.

---

## Deployment Guide

### 1. Setup OCI Streaming
Create a Stream to act as the message bus:
1. Go to **Analytics & AI** > **Messaging** > **Streaming**.
2. Create a **Stream Pool** (Private Endpoint recommended).
3. Create a **Stream** named `node-maintenance-stream`.
4. Note the **Messages Endpoint** and **Stream OCID**.

### 2. Configure IAM Policies
Create a **Dynamic Group** containing your OKE worker nodes:

**Dynamic Group Rule:**
```text
Any {instance.compartment.id = 'ocid1.compartment.oc1..example'}
Use code with caution.
```

Policy for the Dynamic Group:
```text
Allow dynamic-group <Group_Name> to use stream-family in compartment <Compartment_Name>
Allow dynamic-group <Group_Name> to inspect instances in compartment <Compartment_Name>
```

3. Create the OCI Event Rule
Go to Observability & Management > Events Service > Rules.
Create a Rule:
Service Name: Compute
Event Type: Instance - Maintenance Rescheduled
Action:
Action Type: Streaming
Stream: node-maintenance-stream

4. Deploy to OKE
Apply the manifests:
bash
# 1. Create namespace
kubectl create namespace wd

# 2. Apply RBAC
kubectl apply -f k8s/rbac.yaml

# 3. Deploy Watchdog
kubectl apply -f k8s/deployment.yaml


Required Environment Variables:
Variable	Description
WD_STREAM_ID	The OCID of your OCI Stream.
WD_STREAM_ENDPOINT	Your Messages Endpoint URL.
WD_NODEPOOL             OKE nodepool name
WD_NAMESPACE            Kubernetes namespace used by ONMH 

🔍 Verification
Simulate an event via OCI CLI:
bash
ENCODED_VAL=$(echo '{"eventType": "com.oraclecloud.computeapi.maintenancerescheduled", "data": {"resourceId": "ocid1.instance.oc1..example"}}' | base64)
oci streaming stream message put --stream-id <OCID> --messages '[{"key": "dGVzdA==", "value": "'$ENCODED_VAL'"}]' --endpoint <Endpoint>
Use code with caution.

Check logs:
kubectl logs -f -n wd -l app=oci-node-maintenance-handler

## 🏗 Architecture Diagram

The flow of events from OCI infrastructure to your Kubernetes workload migration:

```mermaid
graph TD
    A[OCI Compute Node] -->|Maintenance Event| B[OCI Events Service]
    B -->|Push Event| C[OCI Streaming]
    C -->|Pull Messages| D[ONMH Watchdog Pod]
    D -->|K8s API: Create| E{Lead Time Check}
    E -->|> 15 mins| F[Kubernetes CronJob]
    E -->|< 15 mins| G[Kubernetes Job]
    F -->|Triggers| H[Drain Pod]
    G -->|Executes| H
    H -->|kubectl drain| I[Target Worker Node]
    I -->|Evict Pods| J[Healthy Worker Nodes]



