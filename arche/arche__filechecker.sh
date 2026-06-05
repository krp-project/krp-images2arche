#/bin/bash
echo "run filechecker"
if [ -z "${PROTOCOL_DIR:-}" ] || [ -z "${PROTOCOL_ID:-}" ]; then
    echo "Error: PROTOCOL_DIR and PROTOCOL_ID must be set in the environment."
    echo "Hint: source ./set_protocol_id.sh"
    exit 1
fi
rm -rf ${PWD}/${PROTOCOL_ID} && mkdir ${PWD}/${PROTOCOL_ID}
docker run \
  --rm \
  --network="host" \
  -v ${PWD}/${PROTOCOL_ID}:/reports \
  -v /home/csae8092/Schreibtisch/krp_0135-0195/${PROTOCOL_ID}:/data \
  --entrypoint arche-filechecker \
  acdhch/arche-ingest \
  --overwrite --skipWarnings /data /reports
