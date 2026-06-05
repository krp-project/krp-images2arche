# krp-images2arche

Repo to generate ARCHE-RDF from KRP images

## set protocol ID

Adapt `/set_protocol_id.sh` so it matches the folder/protocol you'd like to process.

```bash
source ./set_protocol_id.sh
```

## compress tifs

compress tifs in the given folder

```bash
./arche/compress_tiffs.sh
```

## run filechecker

```bash
./arche/arche__filechecker.sh
```
