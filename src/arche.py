import glob
import os
import re  # for capturing sub-collection IDs from filename pattern
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

# create regex pattern object for capturing sub-collection IDs from filenames:
# presuppose conventional filenaming, but allow for hyphen-underscore inconsistency
pattern = re.compile("^(" + re.escape(PROTOCOL_ID) + r"_[a-z]+\d*)[-_]\d{4}\.TIF$")

PROTOCOL_URI = URIRef(f"{TOP_COL_URI}/{PROTOCOL_ID}")
g.add((PROTOCOL_URI, RDF.type, ACDH["Collection"]))
g.add((PROTOCOL_URI, ACDH["isPartOf"], TOP_COL_URI))
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasTitle"],
        Literal(f"{MD_DATA['title']} {MD_DATA['written_date']}", lang="de"),
    )
)
g.add(
    (
        PROTOCOL_URI,
        ACDH["hasAlternativeTitle"],
        Literal(f"{MD_DATA['period']['value']}", lang="de"),
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

# create set for matching sub-collection IDs and list of unmatched filenames
sub_coll_ids = set()
unmatched = []

for x in files:
    f_name = os.path.split(x)[-1]

    # validate filename against pattern:
    # store valid sub-collection IDs in set; relegate unmatched filenames to list
    match = pattern.match(f_name)
    if match:
        sub_coll_id = match.group(1)
        sub_coll_ids.add(sub_coll_id)
    else:
        unmatched.append(f_name)
        continue

    # add sub-collection triples (idempotently)
    # TODO: map IDs to proper titles, add descriptions
    sub_coll_uri = URIRef(f"{TOP_COL_URI}/{sub_coll_id}")
    g.add((sub_coll_uri, RDF.type, ACDH["Collection"]))
    g.add((sub_coll_uri, ACDH["isPartOf"], PROTOCOL_URI))

    subj = URIRef(f"{TOP_COL_URI}/{f_name}")
    g.add((subj, RDF.type, ACDH["Resource"]))
    g.add(
        (subj, ACDH["isPartOf"], sub_coll_uri)
    )  # point to sub-collection (instead of protocol collection)
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

if unmatched:
    print(f"{len(unmatched)} file(s) do not match naming convention: {unmatched}")

g.serialize(out_file)
