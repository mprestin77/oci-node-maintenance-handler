set -x

# Encode the file 'event.json' into a variable
ENCODED_JSON=$(base64 -w 0 $1)

# Use it in the CLI command
oci streaming stream message put \
  --stream-id ocid1.stream.oc1.iad.amaaaaaa22cz7wqar4hixoqhpcmddok5wor2txxbisu7h3iwrrlwpi5tcq3a \
  --messages '[{"key": "bWFpbnRlbmFuY2U=", "value": "'$ENCODED_JSON'"}]' \
  --endpoint https://rdz33fyp7etq.streaming.us-ashburn-1.oci.oraclecloud.com 
