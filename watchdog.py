import oci
import time
import subprocess
import json
import os

from base64 import b64decode

def get_cursor_by_group(sc, sid, group_name, instance_name):
    print(" Creating a cursor for group {}, instance {}".format(group_name, instance_name), flush=True)
    cursor_details = oci.streaming.models.CreateGroupCursorDetails(group_name=group_name, instance_name=instance_name,
                                                                   type=oci.streaming.models.
                                                                   CreateGroupCursorDetails.TYPE_TRIM_HORIZON,
                                                                   commit_on_get=True)
    response = sc.create_group_cursor(sid, cursor_details)
    return response.data.value

def simple_message_loop(client, stream_id, initial_cursor):
    cursor = initial_cursor
    while True:
        get_response = client.get_messages(stream_id, cursor, limit=10)
        #If the stream is empty - wait 5 sec and check again
        if not get_response.data:
            time.sleep(5)

        # Process the messages
        if len(get_response.data)>0:
           print(" Read {} message(s)".format(len(get_response.data)), flush=True)

        for message in get_response.data:
            try:
#              print(b64decode(message.value.encode()).decode())
              msg_body = json.loads(b64decode(message.value.encode()).decode())
              maintenance_events = { 
                      'com.oraclecloud.computeapi.instancemaintenance',
                      'com.oraclecloud.computeapi.instancemaintenance.begin',
                      'com.oraclecloud.computeapi.instancemaintenance.end',
              }
              if msg_body['eventType'] in maintenance_events and msg_body['source']=='ComputeApi':
                 event_type = msg_body['eventType']
                 start_time=msg_body['data']['additionalDetails']['timeWindowStart']
                 instance_ocid = msg_body['data']['additionalDetails']['instanceId']
                 maintenance_reason = msg_body['data']['additionalDetails']['maintenanceReason']

              else:
                 raise Exception("Unknown event")

              print(" Event Type: {0}\n Start Time: {1}\n Instance OCID: {2}\n Maintenance Reason: {3}\n".format(event_type, start_time, instance_ocid, maintenance_reason), flush=True)

              # Create a new job and pass the file name and job name
              p = subprocess.run(['python3', 'new_job.py', instance_ocid, event_type, start_time])
            except subprocess.CalledProcessError as e:
                print(e, flush=True)
                exit(1)
            except Exception as e:
                print(e, flush=True)

        # get_messages is a throttled method; clients should retrieve sufficiently large message
        # batches, as to avoid too many http requests.
        time.sleep(1)
        # use the next-cursor for iteration
        cursor = get_response.headers["opc-next-cursor"]


def main():
  try:
    oci_message_endpoint = os.environ['WD_STREAM_ENDPOINT']
    oci_stream_ocid = os.environ['WD_STREAM_OCID']

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    stream_client = oci.streaming.StreamClient(config={}, signer=signer, service_endpoint=oci_message_endpoint)

# A cursor can be created as part of a consumer group.
# Committed offsets are managed for the group, and partitions
# are dynamically balanced amongst consumers in the group.
    group_cursor = get_cursor_by_group(stream_client, oci_stream_ocid, "wd-group", "wd-instance-1")
    simple_message_loop(stream_client, oci_stream_ocid, group_cursor)

  except Exception as e:
    print("ERROR: "+str(e), flush=True)
    raise Exception(e)

if __name__ == '__main__':
    main()

