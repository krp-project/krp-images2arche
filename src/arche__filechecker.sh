#/bin/bash
echo "run filechecker"
PROTOCOL_ID=krp-0169
rm -rf ${PWD}/${PROTOCOL_ID} && mkdir ${PWD}/${PROTOCOL_ID}
docker run \
  --rm \
  --network="host" \
  -v ${PWD}/${PROTOCOL_ID}:/reports \
  -v /home/csae8092/Schreibtisch/krp_0135-0195/${PROTOCOL_ID}:/data \
  --entrypoint arche-filechecker \
  acdhch/arche-ingest \
  --overwrite --skipWarnings /data /reports
