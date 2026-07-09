import glob
import os
import re  # for capturing sub-collection IDs from filename pattern
import shutil
from collections import (
    Counter,  # import Counter class for counting scans for sub-collection description
)

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

# collect digitising-agent infos in list of tuples
DIGITISING_AGENTS = [
    (URIRef("https://orcid.org/0009-0005-3560-3500"), "Anna", "Holzer"),
    (URIRef("https://d-nb.info/gnd/131679384"), "Richard", "Lein"),
    (URIRef("https://orcid.org/0009-0007-5210-3713"), "Ina", "Schotzko"),
    (URIRef("https://orcid.org/0009-0007-9895-7212"), "Dominik", "Sölkner"),
    (URIRef("https://orcid.org/0009-0006-8542-4743"), "Aliana", "Martinez Despaigne"),
    (URIRef("https://orcid.org/0009-0005-4167-5041"), "Georg", "Hubalek"),
]

# collect 2nd metadata-creator infos in tuple
tfruehwirth = (URIRef("https://orcid.org/0000-0002-3997-5193"), "Timo", "Frühwirth")

# map image file letter code to document-part names
PARTS_MAP = {
    "a": "Anhang",
    "b": "Beilage",
    "k": "Konzept",
    "r": "Reinschrift",
    "s": "Stenogramm",
    "t": "Tagesordnung",
    "z": "Zusätze",
}
permitted_letters = "".join(
    PARTS_MAP.keys()
)  # save permitted letters from PARTS_MAP (single source of truth)

img_dir = os.path.join(BASE_PATH, PROTOCOL_ID)

# create regex pattern object for capturing sub-collection IDs from filenames:
# presuppose conventional filenaming, but allow for hyphen-underscore inconsistency
pattern = re.compile(
    rf"^({re.escape(PROTOCOL_ID)}_([{permitted_letters}])(\d*))[-_]\d{{4}}\.TIF$"
)

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
# g.add(
#     (
#         PROTOCOL_URI,
#         ACDH["hasAlternativeTitle"],
#         Literal(f"{MD_DATA['period']['value']}", lang="de"),
#     )
# )
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
# add 2nd metadata creator to collection
g.add((PROTOCOL_URI, ACDH["hasMetadataCreator"], tfruehwirth[0]))

files = glob.glob(f"{img_dir}/**/*.TIF", recursive=True)

# create set for matching sub-collection IDs and list of unmatched filenames
sub_coll_ids = set()
unmatched = []

# create set for holding names of all sub-collections inside collection
sub_coll_names = set()

# create counter for scans in sub-collections (no idempotency)
sub_coll_counts = Counter()
for x in files:
    m = pattern.match(os.path.split(x)[-1])
    if m:
        sub_coll_counts[m.group(1)] += (
            1  # increment count (value) of specific sub-collection (key)
        )

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

    # create sub-collection name from regex capture groups
    if match.group(3):
        sub_coll_name = f"{PARTS_MAP[match.group(2)]} {match.group(3)}"
    else:
        sub_coll_name = PARTS_MAP[match.group(2)]

    # add freshly created sub-collection name to set
    sub_coll_names.add(sub_coll_name)

    # concatenate sub-collection description
    sub_coll_desc = f"{sub_coll_name} zu {MD_DATA['title']} {MD_DATA['written_date']}, bestehend aus {sub_coll_counts[sub_coll_id]} digitalisierten Seite(n)"

    # add sub-collection triples once (idempotently)
    sub_coll_uri = URIRef(f"{TOP_COL_URI}/{sub_coll_id}")
    g.add((sub_coll_uri, RDF.type, ACDH["Collection"]))
    g.add((sub_coll_uri, ACDH["isPartOf"], PROTOCOL_URI))
    g.add((sub_coll_uri, ACDH["hasTitle"], Literal(sub_coll_name, lang="de")))
    g.add(
        (sub_coll_uri, ACDH["hasDepositor"], URIRef("https://d-nb.info/gnd/120789825"))
    )
    g.add((sub_coll_uri, ACDH["hasDescription"], Literal(sub_coll_desc, lang="de")))
    # add 2nd metadata creator to sub-collection
    g.add((sub_coll_uri, ACDH["hasMetadataCreator"], tfruehwirth[0]))

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
    # loop through digitising-agent infos
    for uri, firstname, lastname in DIGITISING_AGENTS:
        g.add(
            (subj, ACDH["hasDigitisingAgent"], uri)
        )  # add digitising agents to each image
        # add person triples once (idempotently)
        g.add((uri, RDF.type, ACDH["Person"]))
        g.add((uri, ACDH["hasFirstName"], Literal(firstname, lang="de")))
        g.add((uri, ACDH["hasLastName"], Literal(lastname, lang="de")))
    for p, o in arche_constants.predicate_objects():
        g.add((subj, p, o))
    # add 2nd metadata creator to resource once (idempotently)
    g.add((subj, ACDH["hasMetadataCreator"], tfruehwirth[0]))

# concatenate collection description and add hasDescription triple
coll_desc = f"{MD_DATA['title']} {MD_DATA['written_date']}, bestehend aus {len(sub_coll_names)} Teilen: {', '.join(sorted(sub_coll_names))}"
g.add((PROTOCOL_URI, ACDH["hasDescription"], Literal(coll_desc, lang="de")))

# add 2nd metadata creator to top collection
g.add((TOP_COL_URI, ACDH["hasMetadataCreator"], tfruehwirth[0]))
# add 2nd-metadata-creator infos
g.add((tfruehwirth[0], RDF.type, ACDH["Person"]))
g.add((tfruehwirth[0], ACDH["hasFirstName"], Literal(tfruehwirth[1], lang="de")))
g.add((tfruehwirth[0], ACDH["hasLastName"], Literal(tfruehwirth[2], lang="de")))

# output console feedback on unmatched file names for the mechanism to fail informatively
if unmatched:
    print(f"{len(unmatched)} file(s) do not match naming convention: {unmatched}")

g.serialize(out_file)
