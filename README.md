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
*   **Event-Driven Automation:** Integrates with the **OCI Event Service** to react to maintenance notifications in real-time, providing a high-performance, push-based alternative to polling.
*   **Intelligent Scheduling:** Features a built-in logic engine to calculate lead times, ensuring node evacuation triggers precisely 15 minutes before maintenance begins.
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

### 3. Create OCI Event Rule
Go to **Observability & Management** > **Events Service** > **Rules**.
Create an event rule with **Condition** set to **Event Type** and **Service Name** set to **Compute**. Add the following filters in **Event Type**:
```text
Instance Maintenance
Instance Maintenance-begin
Instance Maintenance-end
```
Under Actions set **Action Type** to **Streaming**, set **Compartment** to the stream compartent and select the stream that was created in [Setup OCI Streaming](https://github.com/mprestin77/oci-node-maintenance-handler/blob/master/README.md#1-setup-oci-streaming)

![image](https://github.com/mprestin77/oci-node-maintenance-handler/blob/master/images/EventRule.png)


### 4. Deploy to OKE

#### Install Prerequsites  
*   **Docker Engine:** [Install and start Docker](https://docs.docker.com) to build and run the handler image.
*   **kubectl:** [Install the Kubernetes CLI](https://kubernetes.io) to manage cluster resources.
*   **OCI CLI:** [Install and configure the OCI CLI](https://docs.oracle.com) with a valid configuration file for cluster access and local testing.
*   **OKE Cluster Access:** Ensure you have [configured cluster access](https://docs.oracle.com) via your `kubeconfig` file.

#### Copy Files from Github
Install [git](https://github.com/git-guides/install-git) and clone the repository to your local machine or OCI staging VM:
```text
git clone https://github.com/mprestin77/oci-node-maintenance-handler.git
```
This command creates a directory named oci-node-maintenance-handler containing the source files. After cloning, navigate into the new directory to begin the setup.

#### Login to OCI Container Registry

If you are planning to store ONMH container image in OCI Container Registry (OCIR), create a repo in the region you are going to use. Here is a list of [OCI Registry endpoints per region](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryprerequisites.htm)
Generate Auth Token and log into the Registry using the Auth Token as your password as described in [Logging OCI Registry](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionslogintoocir.htm). As an example I am using 'iad' for us-ashburn-1 region
```text
docker login -u '<tenancy-namespace>/<identity-domain-name>/<user-name>' iad.ocir.io
```
where tenancy-namespace is your OCI [tenancy object storage namespace](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/understandingnamespaces.htm). Enter password and check that it returns **Login Succeeded**.

#### Build Watchdog Container Image
To build **Watchdog** container image go to the directory where you cloned the files and run the following command:
```text
docker build -t watchdog:1.0 .
```
Make sure that the container image is successfully created, and check that with 'docker images' command:
```text
docker images
IMAGE                                            ID             DISK USAGE   CONTENT SIZE   EXTRA      
watchdog:1.0                                     c33d8a46f682        873MB          146MB       
```
If you are using OCI Container Registry push the container image to OCIR. Tag the image using docker command:
```text
docker push <registry-code>/<tenancy-namespace>/<repo-name>:<version>
```
For example, to push the image to OCIR in us-ashburn-1 region use the following command:
```text
docker push iad.ocir.io/<tenancy-namespace>/wd/watchdog:1.0
```
where tenancy-namespace is your OCI [tenancy object storage namespace](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/understandingnamespaces.htm). If you encounter any errors refer to [Pushing Images using Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm). 

*Note: This example shows how to push images to OCIR, but if you prefer using a different container registry push the image to the registry you want to use.*
 
#### Create Namespace
Create a Kubernetes namespace used by ONMH containers: 
```text
kubectl create namespace wd
```

#### Create Config Map
Edit config.map file and set the following environment variables:
```text
WD_STREAM_ID	        "OCID of your OCI Stream"
WD_STREAM_ENDPOINT	    "Messages Endpoint URL"
WD_NODEPOOL             "OKE nodepool name"
WD_NAMESPACE            "Kubernetes namespace used by ONMH jobs" 
```

Create the config map:
```text
kubectl -n wd apply -f config.map
```

#### Apply RBAC
Create Kubernetes RBAC role and sevice account:
```text
kubectl -n wd apply -f rbac.yaml
```

#### Create Image Pull Secret
If you store the ONMH image in a private OCI Container Registry (OCIR), you must create a secret so Kubernetes can pull the image:

```bash
kubectl create secret docker-registry ocirsecret \
  -n wd \
  --docker-server=<region-code>.ocir.io \
  --docker-username='<tenancy-namespace>/<username>' \
  --docker-password='<auth-token>' \
  --docker-email='<email-address>'
```
  
#### Deploy a Watchdog Container
Edit wd.yaml file and replace image repo with your registry:  
```text
image: <region-code>.ocir.co/<tenancy-namespace>/wd/watchdog:1.0
```
*Note: If you are using a private container registry, insure that the secret name matches the secret that you created to pull the image.*

Update **nodeSelector** in the deployment manifest to specify the node pool where maintenance jobs will be executed. It must match the name of the nodepool configured in [config map](https://github.com/mprestin77/oci-node-maintenance-handler/tree/master#create-config-map). 
```text
nodeSelector:
   name: <your-nodepool-name>
```
*Note: It is highly recommended to use a dedicated node pool for these jobs to ensure the drain process is not interrupted by the maintenance of the node it is running on.*

Deploy Watchdog container:
```text
kubectl -n wd apply -f wd.yaml
```

To check that Watchdog container is running:
```text
kubectl -n wd get pods
NAME                                                READY   STATUS      RESTARTS   AGE
wd-6bdbb448ff-h54ln                                 1/1     Running     0          10s
```
If the status is not "Running" get the pod logs to see the error, for example:
```text
kubectl -n wd describe pod wd-6bdbb448ff-h54ln
```

#### Verify that ONMH is Working
Go to **Observability & Management** > **Events Service** > **Rules**. Open the event rule that you created and click on "View example events (JSON). In **Event Type** select **Instance Maintenance Event - Scheduled**.
it shows event JSON, for example:
```text
{
  "eventType": "com.oraclecloud.computeapi.instancemaintenance",
  "cloudEventsVersion": "0.1",
  "eventTypeVersion": "2.0",
  "source": "ComputeApi",
  "eventTime": "2023-08-18T12:00:00.000Z",
  "contentType": "application/json",
  "data": {
    "compartmentId": "ocid1.compartment.oc1..unique_ID",
    "compartmentName": "example_compartment",
    "resourceName": "maintenance_name",
    "resourceId": "ocid1.instancemaintenanceevent.oc1.phx.unique_ID",
    "availabilityDomain": "availability_domain",
    "additionalDetails": {
      "instanceId": "ocid1.instance.oc1.phx.<unique_ID>",
      "lifecycleState": "SCHEDULED",
      "maintenanceCategory": "FLEXIBLE",
      "canReschedule": true,
      "description": "Oracle scheduled a required maintenance action for your instance.",
      "maintenanceReason": "HARDWARE_REPLACEMENT",
      "instanceAction": "None",
      "alternativeResolutionActions": [
        "REBOOT_MIGRATE",
        "TERMINATE"
      ],
      "timeWindowStart": "2023-09-18T12:00:00.000Z",
      "startWindowDuration": "P1D",
      "estimatedDuration": "P5D",
      "correlationToken": "",
      "schemaVersion": 1
    }
  },
  "eventID": "unique_ID",
  "extensions": {
    "compartmentId": "ocid1.compartment.oc1..unique_ID"
  }
}
```
Copy the event JSON to a file your current directory and replace the values for the following attributes:
```text
compartmentId 
instanceId
timeWindowStart
```
Set **compartmentId** to your compartment OCID, **instanceId** to your instance OCID, and **timeWindowStart** to the current UTC time (add 5-10 minutes to it to make sure that the time has not passed yet).  

Create a shell script using OCI CLI:
```text
# Encode the file 'event.json' into a variable
ENCODED_JSON=$(base64 -w 0 $1)

# Use it in the CLI command:
oci streaming stream message put \
  --stream-id ocid1.stream.oc1.iad.amaaaaaa22cz7wqar4hixoqhpcmddok5wor2txxbisu7h3iwrrlwpi5tcq3a \
  --messages '[{"key": "bWFpbnRlbmFuY2U=", "value": "'$ENCODED_JSON'"}]' \
  --endpoint https://rdz33fyp7etq.streaming.us-ashburn-1.oci.oraclecloud.com 
```

Save the script as send_event.sh. Add executable permission to the script and run it:
```text
chmod +x send_event.sh
./send_event.sh  <JSON file name>
```

Check Watchdog logs:
```test
kubectl -n wd logs -f -l app=watchdog

 Creating a cursor for group wd-group, instance wd-instance-1
Instance name: oke-cbthogqqnma-nbns46fu7gq-sxmiigemzuq-3
Found node name: 10.0.10.109
Nodepool: wd-nodepool
Namespace: wd
Creating drain cron job
Job created. status='{'active': None, 'last_schedule_time': None, 'last_successful_time': None}'
```

Check that the cronjob was created, for example:
```text
kubectl -n wd get cronjobs
NAME                                 SCHEDULE      TIMEZONE   SUSPEND   ACTIVE   LAST SCHEDULE   AGE
scheduled-drain-10.0.10.109-011213   45 2 10 2 *   <none>     False     0        <none>          2m35s
```

Monitor the running job. 15 min before the maintenance time you should see the drain job running:
```text
kubectl -n wd get jobs --watch
NAME                                          STATUS     COMPLETIONS   DURATION   AGE
immediate-drain-10.0.10.109-165631            Running   1/1           15s        32h
```
Once the job status is "Complete" check that the node is cordoned and drained, for example:
```text
kubectl get nodes
NAME          STATUS                     ROLES   AGE   VERSION
10.0.10.102   Ready                      node    13d   v1.34.1
10.0.10.109   Ready,SchedulingDisabled   node    12d   v1.34.1
10.0.10.211   Ready                      node    12d   v1.34.1
10.0.10.51    Ready                      node    14d   v1.33.1

kubectl get pods --all-namespaces --field-selector spec.nodeName='10.0.10.109' | grep -v kube-system
NAMESPACE     NAME                      READY   STATUS    RESTARTS   AGE
```

To check that the node is uncordoned after node maintenance ends, repeat this step with **Event Type** set to **Instance Maintenance Event - End**. After sending this event using send_event.sh script the node must be uncordoned:
```text
kubectl get nodes
NAME          STATUS                     ROLES   AGE   VERSION
10.0.10.102   Ready                      node    13d   v1.34.1
10.0.10.109   Ready                      node    12d   v1.34.1
10.0.10.211   Ready                      node    12d   v1.34.1
10.0.10.51    Ready                      node    14d   v1.33.1
```

## Architecture Diagram

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



