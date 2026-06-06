#/bin/bash

echo "ingest binaries for ${TOPCOLID} into ${ARCHE}"
# cp ./arche/title-image.jpg ./to_ingest/title-image.jpg
docker run --rm \
  -v /home/csae8092/Schreibtisch/krp_0135-0195/krp-0169/tif/krp-0169_a/TIF:/data \
  --network="host" \
  --entrypoint arche-import-binary \
  acdhch/arche-ingest \
  /data ${TOPCOLID}/ ${ARCHE} ${ARCHE_USER} ${ARCHE_PASSWORD} --concurrency 10 --skip not_exist
