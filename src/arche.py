import glob
import os
import shutil

import requests
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

to_ingest = "to_ingest"
out_file = os.path.join(to_ingest, "arche.ttl")
shutil.rmtree(to_ingest, ignore_errors=True)
os.makedirs(to_ingest, exist_ok=True)
g = Graph().parse("arche/arche_top_col.ttl")
arche_constants = Graph().parse("arche/arche_constants.ttl")
TOP_COL = os.environ.get("TOPCOLID", "https://id.acdh.oeaw.ac.at/krp")
TOP_COL_URI = URIRef(TOP_COL)
ACDH = Namespace("https://vocabs.acdh.oeaw.ac.at/schema#")


BASE_PATH = os.environ.get("PROTOCOL_DIR")
PROTOCOL_ID = os.environ.get("PROTOCOL_ID")
MD_FILE = requests.get(
    "https://raw.githubusercontent.com/krp-project/krp-baserow-dump/refs/heads/main/json_dumps/protocols.json"
).json()

MD_DATA = {value["krp_id"]: value for key, value in MD_FILE.items()}[PROTOCOL_ID]
print(MD_DATA)

img_dir = os.path.join(BASE_PATH, PROTOCOL_ID)

PROTOCOL_URI = URIRef(f"{TOP_COL_URI}/{PROTOCOL_ID}")
g.add((PROTOCOL_URI, RDF.type, ACDH["Collection"]))
g.add((PROTOCOL_URI, ACDH["isPartOf"], TOP_COL_URI))
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasTitle"],
        Literal(f"{MD_DATA['title']}, {MD_DATA['written_date']}", lang="de"),
    )
)
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasCoverageStartDate"],
        Literal(MD_DATA["date"], datatype=XSD.date),
    )
)
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasCoverageEndDate"],
        Literal(MD_DATA["date"], datatype=XSD.date),
    )
)
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasMetadataCreator"],
        URIRef("https://id.acdh.oeaw.ac.at/pandorfer"),
    )
)
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasNonLinkedIdentifier"],
        Literal(f"{MD_DATA['orig_file_name'].replace('.docx', '')}"),
    )
)
g.add((PROTOCOL_URI, ACDH["hasDepositor"], URIRef("https://d-nb.info/gnd/120789825")))


files = glob.glob(f"{img_dir}/**/*.TIF", recursive=True)

for x in files:
    f_name = os.path.split(x)[-1]
    subj = URIRef(f"{TOP_COL_URI}/{f_name}")
    g.add((subj, RDF.type, ACDH["Resource"]))
    g.add((subj, ACDH["isPartOf"], PROTOCOL_URI))
    g.add((subj, ACDH["hasTitle"], Literal(f"{MD_DATA['title']}: {f_name}", lang="de")))
    g.add(
        (
            subj,
            ACDH["hasCategory"],
            URIRef("https://vocabs.acdh.oeaw.ac.at/archecategory/image"),
        )
    )
    g.add((subj, ACDH["hasDigitisingAgent"], URIRef("https://id.acdh.oeaw.ac.at/none")))
    for p, o in arche_constants.predicate_objects():
        g.add((subj, p, o))

g.serialize(out_file)
