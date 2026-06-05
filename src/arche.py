import json
import os
import shutil

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from tqdm import tqdm

to_ingest = "to_ingest"
out_file = os.path.join(to_ingest, "arche.ttl")
shutil.rmtree(to_ingest, ignore_errors=True)
os.makedirs(to_ingest, exist_ok=True)
g = Graph().parse("arche/arche_top_col.ttl")
arche_constants = Graph().parse("arche/arche_constants.ttl")
TOP_COL = os.environ.get("TOPCOLID", "https://id.acdh.oeaw.ac.at/krp")
TOP_COL_URI = URIRef(TOP_COL)
ACDH = Namespace("https://vocabs.acdh.oeaw.ac.at/schema#")

BASE_PATH = os.environ.get()