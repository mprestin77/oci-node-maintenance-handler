import os
import sys
from kubernetes import client, config
from datetime import datetime, timedelta, timezone
import oci

def get_instance_name(instance_ocid):

    # Initialize the Compute Client using instance principal
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    compute_client = oci.core.ComputeClient(config={}, signer=signer)

    try:
        # Fetch instance details
        response = compute_client.get_instance(instance_id=instance_ocid)
        instance_details = response.data

        return instance_details.display_name

    except oci.exceptions.ServiceError as e:
        return f"Error: {e.message}"

def create_drain_job(hostname, m_start=None):
    # Initialize Clients
    config.load_incluster_config() # <-- IMPORTANT
    batch_v1 = client.BatchV1Api()
    v1 = client.CoreV1Api()

    # Resolve Hostname to Node Name
    nodes = v1.list_node(label_selector=f"hostname={hostname}")
    if nodes is None:
        raise Exception(f"Node {hostname} not found")
    node_name = nodes.items[0].metadata.name
    print(f"Found node name: {node_name}", flush=True)

    # Define namespace and nodepool the job will run
    nodepool_name = os.environ.get('WD_NODEPOOL')
    namespace = os.environ.get('WD_NAMESPACE', 'default')
    # Configure k8s jobs parameters
    ttl_seconds_after_finished = os.environ.get('WD_TTL_SECONDS_AFTER_FINISHED',3600)
    backoff_limit = = os.environ.get('WD_BACKOFF_LIMIT',6)

    now = datetime.now(timezone.utc)
    # Set time zone in the cronjob time
    if m_start is not None and m_start.tzinfo is None:
        m_start = m_start.replace(tzinfo=timezone.utc)

    # Create a cronjob to drain the node 15 min before node maintenance starts. Otherwise execute an immediate drain job
    if m_start is not None and (m_start-now > timedelta(minutes=15)): 
       t = m_start - timedelta(minutes=15)
       timestamp = now.strftime("%H%M%S")

       cronjob_name = f"scheduled-drain-{node_name}-{timestamp}"
       # Format: minute hour day month day_of_week
       cron_schedule = f"{t.minute} {t.hour} {t.day} {t.month} *"

       # Define CronJob Object
       print("Creating drain cron job", flush=True)
       cronjob = client.V1CronJob(
           api_version="batch/v1",
           kind="CronJob",
           metadata=client.V1ObjectMeta(name=cronjob_name),
           spec=client.V1CronJobSpec(
               schedule=cron_schedule,
               job_template=client.V1JobTemplateSpec(
                   spec=client.V1JobSpec(
                      ttl_seconds_after_finished=ttl_seconds_after_finished,
                      backoff_limit=backoff_limit,
                      template=client.V1PodTemplateSpec(
                        spec=client.V1PodSpec(
                            service_account_name="wd-service", # Ensure RBAC exists
                            restart_policy="OnFailure",
                            node_selector=client.V1LocalObjectReference(name=nodepool_name),
                            containers=[client.V1Container(
                                name="kubectl",
                                image="docker.io/bitnami/kubectl:latest",
                                command=["/bin/sh", "-c", 
                                         f"kubectl drain {node_name} --ignore-daemonsets --delete-emptydir-data --force --timeout=10m"]
                            )]
                        )
                      )
                   )
               )
           )
       )

       # Create CronJob in the namespace
       try:
          api_response = batch_v1.create_namespaced_cron_job(namespace=namespace, body=cronjob)
          print("Job created. status='%s'" % str(api_response.status), flush=True)
          return api_response
       except Exception as e:
          print(f"Exception when calling BatchV1Api->create_namespaced_cron_job: {e}")
          return None

    else: # Create an immediate job to drain the node
       print("Creating immediate drain job", flush=True)
       timestamp = now.strftime("%H%M%S")
       job_name = f"immediate-drain-{node_name}-{timestamp}"
       job = client.V1Job(
           api_version="batch/v1",
           kind="Job",
           metadata=client.V1ObjectMeta(name=job_name),
           spec=client.V1JobSpec(
             ttl_seconds_after_finished=3600,
             template=client.V1PodTemplateSpec(
               spec=client.V1PodSpec(
                 service_account_name="wd-service", # Ensure RBAC exists
                 restart_policy="OnFailure",
                 node_selector=client.V1LocalObjectReference(name=nodepool_name),
                 containers=[client.V1Container(
                    name="kubectl",
                    image="docker.io/bitnami/kubectl:latest",
                    command=["/bin/sh", "-c",
                             f"kubectl drain {node_name} --ignore-daemonsets --delete-emptydir-data --force --timeout=10m"]
                 )]
               )
             )
           )
       )
       # Create the Job in the namespace
       try:
          api_response = batch_v1.create_namespaced_job(namespace="wd", body=job)
          print("Job created. status='%s'" % str(api_response.status), flush=True)
          return api_response
       except Exception as e:
          print(f"Exception when calling BatchV1Api->create_namespaced_job: {e}")
          return None


def create_uncordon_job(hostname):
    # Initialize Clients
    config.load_incluster_config() # <-- IMPORTANT
    batch_v1 = client.BatchV1Api()
    v1 = client.CoreV1Api()

    # Resolve Hostname to Node Name
    nodes = v1.list_node(label_selector=f"hostname={hostname}")
    if nodes is None:
        raise Exception(f"Node {hostname} not found")
    node_name = nodes.items[0].metadata.name
    print(f"Found node name: {node_name}", flush=True)

    # Define namespace and nodepool the job will run
    nodepool_name = os.environ.get('WD_NODEPOOL')
    namespace = os.environ.get('WD_NAMESPACE', 'default')
    # Configure k8s jobs parameters
    ttl_seconds_after_finished = os.environ.get('WD_TTL_SECONDS_AFTER_FINISHED',3600)
    backoff_limit = os.environ.get('WD_BACKOFF_LIMIT',6)

    # Create an immediate job to uncordon the node
    print("Creating immediate uncordon job", flush=True)
    timestamp = datetime.now().strftime("%H%M%S")
    job_name = f"immediate-uncordon-{node_name}-{timestamp}"
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name),
        spec=client.V1JobSpec(
          ttl_seconds_after_finished=ttl_seconds_after_finished,
          backoff_limit=backoff_limit,
          template=client.V1PodTemplateSpec(
            spec=client.V1PodSpec(
              service_account_name="wd-service", # Ensure RBAC exists
              restart_policy="OnFailure",
              node_selector=client.V1LocalObjectReference(name=nodepool_name),
              containers=[client.V1Container(
                 name="kubectl",
                 image="docker.io/bitnami/kubectl:latest",
                 command=["/bin/sh", "-c",
                          f"kubectl uncordon {node_name}"]
              )]
            )
          )
        )
    )
    try:
       api_response = batch_v1.create_namespaced_job(namespace="wd", body=job)
       print("Job created. status='%s'" % str(api_response.status), flush=True)
       return api_response
    except Exception as e:
       print(f"Exception when calling BatchV1Api->create_namespaced_job: {e}")
       return None


def main():
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.

    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <instance ocid> <event type> <start time>", flush=True)
        exit (1)

    instance_ocid = sys.argv[1]
    event_type = sys.argv[2]
    start_time = sys.argv[3]

    # Get instance name from OCID
    instance_name = get_instance_name(instance_ocid)
    if instance_name is not None:
        print(f"Instance name: {instance_name}", flush=True)
    else:
        print("Failed to get instance name", flush=True)
        exit(1)

    if event_type == 'com.oraclecloud.computeapi.instancemaintenance':
        start_time_iso = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        job = create_drain_job(instance_name, start_time_iso)

    elif event_type == 'com.oraclecloud.computeapi.instancemaintenance.begin':
        job = create_drain_job(instance_name)

    elif event_type == 'com.oraclecloud.computeapi.instancemaintenance.end':
        job = create_uncordon_job(instance_name)

    else:
        print("Unknown event")
        exit(1)

if __name__ == '__main__':
    main()

