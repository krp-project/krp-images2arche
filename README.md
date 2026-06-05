# krp-images2arche

Repo to generate ARCHE-RDF from KRP images

## set protocol ID

Adapt `/protocol_id.env` so it matches the folder/protocol you'd like to process.

```bash
source ./set_env_variables.sh
```

## compress tifs

compress tifs in the given folder

```bash
./src/compress_tiffs.sh
```

## run filechecker

```bash
./arche/arche__filechecker.sh
```

## create arche rdf

```bash
uv run ./src/arche.py
```
