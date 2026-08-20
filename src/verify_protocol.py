#!/usr/bin/env python3
"""Read-only end-to-end verification of one protocol.

Checks the whole pipeline for a single protocol: flash drive -> network share ->
filechecker reports -> arche.ttl, plus the git state. Alters nothing.

Usage:
    python3 src/verify_protocol.py                 # protocol from $PROTOCOL_ID / protocol_id.env
    python3 src/verify_protocol.py krp-0059        # explicit protocol
    python3 src/verify_protocol.py --quick         # skip the per-file pixel comparison
    python3 src/verify_protocol.py --flash /media/me/Drive/KRP

Exit code 0 = everything passed, 1 = at least one check failed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

PARTS_MAP = {
    "a": "Anhang",
    "b": "Beilage",
    "k": "Konzept",
    "r": "Reinschrift",
    "s": "Stenogramm",
    "t": "Tagesordnung",
    "z": "Zusätze",
}
ACDH = "https://vocabs.acdh.oeaw.ac.at/schema#"

# properties every sub-collection (= the CHO handed to Kulturpool) must carry
SUB_COLL_REQUIRED = [
    "hasTitle", "hasDescription", "hasTag", "hasOaiSet", "hasLicense",
    "hasLanguage", "hasOwner", "hasSubject", "hasSpatialCoverage",
    "hasNextItem", "isPartOf", "hasDepositor", "hasMetadataCreator",
]
# properties every image resource must carry
RESOURCE_REQUIRED = [
    "hasTitle", "hasCategory", "hasLicense", "hasOwner", "hasDigitisingAgent",
    "hasCreatedStartDateOriginal", "hasCreatedEndDateOriginal", "isPartOf",
    "hasRightsHolder", "hasLicensor", "hasDepositor", "hasMetadataCreator",
]
# properties the protocol collection must carry
PROTOCOL_REQUIRED = ["hasTitle", "hasDescription", "hasLanguage", "hasNextItem", "isPartOf"]
# forbidden on any collection - the Kulturpool export derives these from resources
COLL_FORBIDDEN = ["hasCreatedStartDateOriginal", "hasCreatedEndDateOriginal"]


class Report:
    """Collects results so the verdict can be printed last."""

    def __init__(self):
        self.failures = []
        self.notes = []
        self.pending = False  # protocol verified but not yet committed
        self.skipped_pixels = False

    def check(self, ok, label, detail=""):
        if not ok:
            self.failures.append(f"{label}{': ' + detail if detail else ''}")
        print(f"  [{'ok' if ok else 'FAIL'}] {label}{'  ' + detail if detail else ''}")
        return ok

    def note(self, text):
        self.notes.append(text)
        print(f"  [note] {text}")


def walk_files(root, suffix=None):
    """Map filename -> directory. Filenames are unique by convention; see count_files."""
    out = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if suffix is None or name.endswith(suffix):
                out[name] = os.path.relpath(dirpath, root)
    return out


def count_files(root, suffix=None):
    """Total files on disk - differs from len(walk_files) iff a basename is duplicated."""
    return sum(
        1
        for _, _, filenames in os.walk(root)
        for name in filenames
        if suffix is None or name.endswith(suffix)
    )


def duplicate_basenames(root, suffix=None):
    seen = Counter()
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if suffix is None or name.endswith(suffix):
                seen[name] += 1
    return [name for name, n in seen.items() if n > 1]


def strip_tif_layer(relpath):
    """The share keeps the source tree minus any TIF/TIFs directory level."""
    parts = [p for p in relpath.split(os.sep) if p.lower() not in ("tif", "tifs")]
    return os.path.join(*parts) if parts else "."


def gdal_info(path):
    """Return (band checksums, 'W, H', compression) - or (None, None, None)."""
    out = subprocess.run(
        ["gdalinfo", "-checksum", path], capture_output=True, text=True
    ).stdout
    size = re.search(r"Size is ([\d, ]+)", out)
    if not size:
        return None, None, None
    return (
        re.findall(r"Checksum=(\d+)", out),
        size.group(1),
        "LZW" if "COMPRESSION=LZW" in out else "NONE",
    )


def stage_share(rep, protocol, flash_dir, share_dir):
    """Flash drive -> share: nothing lost, nothing left behind, correctly flattened."""
    print("\n1 - flash drive -> share")
    if not rep.check(os.path.isdir(share_dir), "share directory exists", share_dir):
        return None, None
    have_source = os.path.isdir(flash_dir)
    if not have_source:
        rep.note(f"flash drive not available ({flash_dir}) - copy checks skipped")

    dst = walk_files(share_dir, ".TIF")
    rep.check(bool(dst), "share holds .TIF files", f"{len(dst)} files")

    # every later check is keyed by filename, so a duplicated basename would hide a file
    for label, root in (("share", share_dir), ("flash drive", flash_dir if have_source else None)):
        if root is None:
            continue
        dupes = duplicate_basenames(root, ".TIF")
        rep.check(
            not dupes and count_files(root, ".TIF") == len(walk_files(root, ".TIF")),
            f"no duplicated filenames on the {label}",
            str(dupes[:5]) if dupes else "",
        )

    if have_source:
        src = walk_files(flash_dir, ".TIF")
        rep.check(
            sorted(src) == sorted(dst),
            "filename sets identical",
            f"flash {len(src)} / share {len(dst)}",
        )
        misplaced = [
            n for n in src
            if n in dst and strip_tif_layer(src[n]) != dst[n]
        ]
        rep.check(
            not misplaced,
            "every file sits where it did, minus the TIF layer",
            f"{len(misplaced)} misplaced: {misplaced[:5]}" if misplaced else "",
        )

    stale = [
        os.path.join(os.path.relpath(dp, share_dir), d)
        for dp, dirs, _ in os.walk(share_dir)
        for d in dirs
        if d.lower() in ("tif", "tifs") or "raw" in d.lower()
    ]
    rep.check(not stale, "no TIF/RAW directories remain", str(stale[:5]) if stale else "")

    empty = [os.path.relpath(dp, share_dir) for dp, dn, fn in os.walk(share_dir) if not dn and not fn]
    rep.check(not empty, "no empty directories", str(empty[:5]) if empty else "")

    all_files = walk_files(share_dir)
    tmp = [n for n in all_files if n.startswith("__tmp__")]
    rep.check(not tmp, "no __tmp__ leftovers from compression", str(tmp[:5]) if tmp else "")

    lower = [n for n in all_files if n.endswith(".tif")]
    rep.check(not lower, "no lowercase .tif files", str(lower[:5]) if lower else "")

    cr2 = [n for n in all_files if n.lower().endswith(".cr2")]
    rep.check(not cr2, "no RAW images on the share", str(cr2[:5]) if cr2 else "")

    non_tif = sorted(n for n in all_files if not n.endswith(".TIF"))
    if non_tif:
        rep.note(f"non-TIF files present (expected once DOCX arrive): {non_tif}")

    return dst, (walk_files(flash_dir, ".TIF") if have_source else None)


def stage_pixels(rep, flash_dir, share_dir, expected):
    """Compression must be lossless: compare decoded pixels against the originals."""
    print("\n2 - compression lossless")
    if not os.path.isdir(flash_dir):
        rep.check(False, "flash drive available for comparison", flash_dir)
        return
    src, dst = walk_files(flash_dir, ".TIF"), walk_files(share_dir, ".TIF")
    # guards: an empty or mismatched comparison must never look like a pass
    if not rep.check(bool(src), "source holds .TIF files to compare", f"{len(src)}"):
        return
    if not rep.check(sorted(src) == sorted(dst), "file sets match before comparing"):
        return

    mismatched, not_lzw, unreadable = [], [], []
    bands, dims = Counter(), Counter()
    for name in sorted(src):
        a = gdal_info(os.path.join(flash_dir, src[name], name))
        b = gdal_info(os.path.join(share_dir, dst[name], name))
        if a[0] is None or b[0] is None:
            unreadable.append(name)
            continue
        bands[len(a[0])] += 1
        dims[a[1]] += 1
        if a[0] != b[0] or a[1] != b[1] or not a[0]:
            mismatched.append(name)
        if b[2] != "LZW":
            not_lzw.append(name)

    verified = len(src) - len(unreadable)
    rep.check(not unreadable, "every file readable", str(unreadable[:5]) if unreadable else "")
    rep.check(
        verified == expected,
        "all files compared",
        f"{verified} of {expected}",
    )
    rep.check(not mismatched, "pixel data identical to originals", str(mismatched[:5]) if mismatched else "")
    rep.check(not not_lzw, "every file LZW-compressed on the share", str(not_lzw[:5]) if not_lzw else "")
    print(f"  [info] bands {dict(bands)} | dimensions {dict(dims)}")


def stage_reports(rep, protocol, share_dir, report_dir):
    """The filechecker reports must describe the share exactly."""
    print("\n3 - filechecker reports")
    if not rep.check(os.path.isdir(report_dir), "report directory exists", report_dir):
        return None

    try:
        errors = json.load(open(os.path.join(report_dir, "error.json")))
    except Exception as exc:  # truncated or missing
        rep.check(False, "error.json readable", str(exc))
        return None
    rep.check(not errors, "error.json empty", str(errors[:3]) if errors else "")

    try:
        entries = json.load(open(os.path.join(report_dir, "fileList.json")))
    except Exception as exc:
        rep.check(False, "fileList.json readable", str(exc))
        return None

    on_disk = walk_files(share_dir)
    rep.check(
        sorted(e["filename"] for e in entries) == sorted(on_disk),
        "fileList matches the share exactly",
        f"report {len(entries)} / disk {len(on_disk)}",
    )
    wrong_dir = [
        e["filename"] for e in entries
        if e["filename"] in on_disk
        and e["directory"] != os.path.join("/data", on_disk[e["filename"]]).replace("/.", "")
    ]
    rep.check(not wrong_dir, "recorded directories match reality", str(wrong_dir[:5]) if wrong_dir else "")
    rep.check(all(e["valid"] for e in entries), "every entry valid")
    foreign = [e["filename"] for e in entries if not e["filename"].startswith(protocol)]
    rep.check(not foreign, "no files from another protocol", str(foreign[:5]) if foreign else "")
    stale = {
        e["directory"] for e in entries
        if e["directory"].split("/")[-1].lower() in ("tif", "tifs")
        or "RAW" in e["directory"].upper()
    }
    rep.check(not stale, "no stale TIF/RAW paths recorded", str(sorted(stale)[:5]) if stale else "")
    return entries


def stage_rdf(rep, protocol, entries, ttl_path, top_col_path, constants_path):
    """arche.ttl must cover every image and satisfy ARCHE + Kulturpool rules."""
    print("\n4 - arche.ttl")
    try:
        from rdflib import Graph, Literal, RDF, URIRef
        from rdflib.compare import isomorphic
    except ImportError:
        rep.check(False, "rdflib available", "pip install rdflib")
        return
    if not rep.check(os.path.isfile(ttl_path), "arche.ttl exists", ttl_path):
        return

    g = Graph()
    try:
        g.parse(ttl_path, format="turtle")
    except Exception as exc:
        rep.check(False, "arche.ttl parses as valid turtle", str(exc)[:150])
        return
    base = "https://id.acdh.oeaw.ac.at/krp"

    def P(name):
        return URIRef(ACDH + name)

    found = sorted(set(re.findall(r"k[rp]{2}-\d{4}", open(ttl_path).read())))
    print(f"  [info] arche.ttl describes: {', '.join(found) or 'nothing'}")
    if not rep.check(
        found == [protocol],
        "arche.ttl holds exactly this protocol",
        f"found {found} - re-run arche.py for {protocol}" if found != [protocol] else "",
    ):
        return

    files = sorted(
        e["filename"] for e in entries
        if e["filename"].endswith(".TIF") and e["valid"]
    )
    pattern = re.compile(
        rf"^({re.escape(protocol)}_([{''.join(PARTS_MAP)}])(\d*))[-_](\d{{4}})\.TIF$"
    )
    sub_files = defaultdict(list)
    unmatched = []
    for name in files:
        m = pattern.match(name)
        sub_files[m.group(1)].append(name) if m else unmatched.append(name)
    rep.check(not unmatched, "every image matches the naming convention", str(unmatched[:5]) if unmatched else "")

    resources = [s for s, _, _ in g.triples((None, RDF.type, P("Resource")))]
    collections = [s for s, _, _ in g.triples((None, RDF.type, P("Collection")))]
    res_names = {str(s).split("/")[-1] for s in resources}
    subs = sorted(str(s) for s in collections if str(s).split("/")[-1] != protocol)

    rep.check(res_names == set(files), "every image has a Resource",
              f"missing {sorted(set(files) - res_names)[:5]} extra {sorted(res_names - set(files))[:5]}"
              if res_names != set(files) else "")
    rep.check(len(subs) == len(sub_files), "sub-collection count matches the filenames",
              f"{len(subs)} vs {len(sub_files)}")

    missing_sub = [
        s.split("/")[-1] for s in subs
        if [p for p in SUB_COLL_REQUIRED if (URIRef(s), P(p), None) not in g]
    ]
    rep.check(not missing_sub, "sub-collections carry every required property", str(missing_sub[:5]) if missing_sub else "")
    # the protocol collection itself is checked too - it was previously only inspected by eye
    protocol_uri = URIRef(f"{base}/{protocol}")
    rep.check((protocol_uri, RDF.type, P("Collection")) in g, "protocol collection typed as Collection")
    missing_protocol = [p for p in PROTOCOL_REQUIRED if (protocol_uri, P(p), None) not in g]
    rep.check(not missing_protocol, "protocol collection carries every required property", str(missing_protocol))
    rep.check(
        (protocol_uri, P("isPartOf"), URIRef(base)) in g,
        "protocol collection is part of the top collection",
    )
    rep.check((URIRef(base), RDF.type, P("TopCollection")) in g, "top collection present and typed")

    forbidden = [
        s.split("/")[-1] for s in subs + [str(protocol_uri)]
        if [p for p in COLL_FORBIDDEN if (URIRef(s), P(p), None) in g]
    ]
    rep.check(not forbidden, "no collection carries resource-only date properties", str(forbidden[:5]) if forbidden else "")

    missing_res = [
        str(r).split("/")[-1] for r in resources
        if [p for p in RESOURCE_REQUIRED if (r, P(p), None) not in g]
    ]
    rep.check(not missing_res, "resources carry every required property", str(missing_res[:5]) if missing_res else "")
    agents = Counter(len(list(g.objects(r, P("hasDigitisingAgent")))) for r in resources)
    rep.check(set(agents) == {6}, "six digitising agents on every resource", str(dict(agents)))
    tagged = sum(
        1 for r in resources
        if (r, P("hasTag"), None) in g or (r, P("hasOaiSet"), None) in g
    )
    rep.check(tagged == 0, "no resource carries hasTag/hasOaiSet", str(tagged))
    # NB: a resource whose name breaks the convention has no derivable parent - do not
    # let that crash the run, report it instead (this is exactly the anomaly case)
    wrong_parent, unparseable = [], []
    for r in resources:
        name = str(r).split("/")[-1]
        m = pattern.match(name)
        if not m:
            unparseable.append(name)
        elif (r, P("isPartOf"), URIRef(f"{base}/{m.group(1)}")) not in g:
            wrong_parent.append(name)
    rep.check(not unparseable, "every Resource name is parseable", str(unparseable[:5]) if unparseable else "")
    rep.check(not wrong_parent, "every resource belongs to its own sub-collection", str(wrong_parent[:5]) if wrong_parent else "")
    titles = [str(o) for s, _, o in g.triples((None, P("hasTitle"), None)) if str(s).endswith(".TIF")]
    rep.check(len(set(titles)) == len(resources), "resource titles all distinct")

    # hasNextItem: protocol -> first sub, each sub -> first image + next sub, images chained
    links = list(g.triples((None, P("hasNextItem"), None)))
    expected = 1 + len(subs) + (len(subs) - 1) + (len(resources) - len(subs))
    rep.check(len(links) == expected, "hasNextItem count", f"{len(links)} of {expected}")
    doubled = [k for k, v in Counter(str(o) for _, _, o in links).items() if v > 1]
    rep.check(not doubled, "no item is pointed at twice", str(doubled[:5]) if doubled else "")
    subjects = {str(s) for s in g.subjects()}
    dangling = {str(o) for _, _, o in links} - subjects
    rep.check(not dangling, "no hasNextItem points into nothing", str(sorted(dangling)[:5]) if dangling else "")

    nxt = {str(a): str(b) for a, _, b in links}
    first = [str(o) for o in g.objects(protocol_uri, P("hasNextItem"))]
    rep.check(len(first) == 1, "protocol points at exactly one first child", str(first))
    # walk the chain, refusing to loop forever if the graph contains a cycle
    chain, cursor, unsorted_subs = [], first[0] if first else None, []
    seen_subs, cycle = set(), None
    while cursor and cursor not in seen_subs:
        seen_subs.add(cursor)
        images, step = [], [
            str(o) for o in g.objects(URIRef(cursor), P("hasNextItem")) if o.endswith(".TIF")
        ]
        walker, seen_images = step[0] if step else None, set()
        while walker and walker.endswith(".TIF") and walker not in seen_images:
            seen_images.add(walker)
            images.append(walker)
            walker = nxt.get(walker)
        if walker in seen_images:
            cycle = f"image cycle in {cursor.split('/')[-1]}"
        if images != sorted(images):
            unsorted_subs.append(cursor.split("/")[-1])
        chain.append(f"{cursor.split('/')[-1].replace(protocol + '_', '')}({len(images)})")
        following = [
            str(o) for o in g.objects(URIRef(cursor), P("hasNextItem")) if not o.endswith(".TIF")
        ]
        cursor = following[0] if following else None
    if cursor in seen_subs and cursor is not None:
        cycle = f"sub-collection cycle at {cursor.split('/')[-1]}"
    rep.check(cycle is None, "no cycle in the hasNextItem chain", cycle or "")
    rep.check(len(chain) == len(subs), "chain visits every sub-collection", f"{len(chain)} of {len(subs)}")
    rep.check(not unsorted_subs, "images chained in filename order", str(unsorted_subs) if unsorted_subs else "")
    reached_images = sum(int(c.split("(")[1].rstrip(")")) for c in chain)
    rep.check(reached_images == len(resources), "chain reaches every image",
              f"{reached_images} of {len(resources)}")
    print(f"  [info] chain: {' -> '.join(chain)}")

    text = [
        str(o) for _, p, o in g
        if isinstance(o, Literal) and str(p).split("#")[-1] in ("hasTitle", "hasDescription")
    ]
    sloppy = [t for t in text if "  " in t or t != t.strip()]
    rep.check(not sloppy, "no stray whitespace in titles/descriptions", str(sloppy[:3]) if sloppy else "")

    persons = {str(s) for s, _, _ in g.triples((None, RDF.type, P("Person")))}
    known = {base, str(protocol_uri)} | set(subs) | {f"{base}/{f}" for f in files} | persons
    unexpected = [str(s) for s in subjects if str(s) not in known]
    rep.check(not unexpected, "no unexpected subjects in the graph", str(unexpected[:5]) if unexpected else "")
    internal = {str(o) for _, _, o in g if isinstance(o, URIRef) and str(o).startswith(base)}
    rep.check(not internal - subjects, "no dangling internal references", str(sorted(internal - subjects)[:5]))

    constants = Graph()
    constants.parse(constants_path, format="turtle")
    wanted = {(str(p), str(o)) for _, p, o in constants}
    missing_consts = [
        f for f in files
        if not wanted.issubset({(str(p), str(o)) for p, o in g.predicate_objects(URIRef(f"{base}/{f}"))})
    ]
    rep.check(not missing_consts, "shared constants applied to every resource", str(missing_consts[:5]) if missing_consts else "")

    top = Graph()
    top.parse(top_col_path, format="turtle")
    source_top = set(top.predicate_objects(URIRef(base)))
    output_top = set(g.predicate_objects(URIRef(base)))
    lost = {str(p).split("#")[-1] for p, _ in source_top - output_top}
    added = {str(p).split("#")[-1] for p, _ in output_top - source_top}
    rep.check(not lost, "top collection keeps every source triple", str(sorted(lost)))
    rep.check(added <= {"hasMetadataCreator"}, "top collection gains only hasMetadataCreator", str(sorted(added)))

    round_trip = Graph()
    round_trip.parse(data=g.serialize(format="turtle"), format="turtle")
    rep.check(isomorphic(g, round_trip), "turtle re-serialises identically")


REPORT_FILES = ["directoryList.json", "droid.csv", "error.json", "fileInfo.jsonl", "fileList.json"]


def stage_git(rep, protocol, repo):
    """Either the reports are committed alone and pushed, or they are ready to be."""
    print("\n5 - git")

    def git(*args):
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True
        ).stdout.strip()

    committed = bool(git("ls-files", "--", protocol))

    # split the working tree into "belongs to this protocol" and everything else.
    # NB: do not strip() the porcelain output - the leading status column matters.
    raw = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    mine, other = [], []
    for line in raw.splitlines():
        if not line.strip():
            continue
        path = line.split(maxsplit=1)[1].strip('"') if len(line.split(maxsplit=1)) > 1 else line
        (mine if path.rstrip("/").split("/")[0] in (protocol, "protocol_id.env") else other).append(path)

    if committed:
        rep.check(not (mine or other), "working tree clean", "; ".join(mine + other)[:200])
        commit = git("log", "-1", "--format=%H", "--", protocol)
        if rep.check(bool(commit), "a commit exists for this protocol"):
            touched = git("show", "--name-only", "--format=", commit).split()
            folders = {p.split("/")[0] for p in touched if p.startswith("krp-")}
            rep.check(folders == {protocol}, "commit touches only this protocol", str(sorted(folders)))
            rep.check(
                f'PROTOCOL_ID="{protocol}"' in git("show", f"{commit}:protocol_id.env"),
                "committed protocol_id.env names this protocol",
            )
        # without an upstream, "git log @{u}..HEAD" prints nothing and would pass vacuously
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if rep.check(bool(upstream), "branch tracks a remote", "" if upstream else "no upstream configured"):
            unpushed = git("log", "--oneline", "@{u}..HEAD")
            rep.check(not unpushed, "everything pushed to the remote",
                      f"{len(unpushed.splitlines())} unpushed commit(s)" if unpushed else "")
    else:
        # run before committing - check the commit *would* be right
        rep.pending = True
        rep.note(f"{protocol} is not committed yet - checking that it is ready to be")
        present = os.listdir(os.path.join(repo, protocol)) if os.path.isdir(os.path.join(repo, protocol)) else []
        missing = [f for f in REPORT_FILES if f not in present]
        rep.check(not missing, "all five report files present", str(missing) if missing else "")
        extra = [f for f in present if f not in REPORT_FILES]
        rep.check(not extra, "no unexpected files in the report folder", str(extra) if extra else "")
        env_line = ""
        env_path = os.path.join(repo, "protocol_id.env")
        if os.path.isfile(env_path):
            env_line = open(env_path).read()
        rep.check(f'PROTOCOL_ID="{protocol}"' in env_line, "protocol_id.env names this protocol")
        if other:
            rep.note(f"also uncommitted, unrelated to {protocol}: {', '.join(other)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("protocol", nargs="?", help="e.g. krp-0059 (default: $PROTOCOL_ID)")
    parser.add_argument("--flash", help="KRP directory on the flash drive")
    parser.add_argument("--quick", action="store_true", help="skip the per-file pixel comparison")
    args = parser.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {}
    env_file = os.path.join(repo, "protocol_id.env")
    if os.path.isfile(env_file):
        for line in open(env_file):
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"')

    protocol = args.protocol or os.environ.get("PROTOCOL_ID") or env.get("PROTOCOL_ID")
    protocol_dir = os.environ.get("PROTOCOL_DIR") or env.get("PROTOCOL_DIR")
    if not protocol or not protocol_dir:
        sys.exit("Could not determine PROTOCOL_ID / PROTOCOL_DIR - pass the protocol as an argument.")

    flash_root = args.flash or os.environ.get("KRP_FLASH")
    if not flash_root:
        for candidate in sorted(
            os.path.join("/media", os.environ.get("USER", ""), d, "KRP")
            for d in os.listdir(os.path.join("/media", os.environ.get("USER", "")))
        ) if os.path.isdir(os.path.join("/media", os.environ.get("USER", ""))) else []:
            if os.path.isdir(candidate):
                flash_root = candidate
                break

    share_dir = os.path.join(protocol_dir, protocol)
    flash_dir = os.path.join(flash_root, protocol) if flash_root else ""
    report_dir = os.path.join(repo, protocol)

    print(f"Verifying {protocol}")
    print(f"  share:  {share_dir}")
    print(f"  flash:  {flash_dir or '(not found)'}")

    rep = Report()
    dst, _ = stage_share(rep, protocol, flash_dir, share_dir)
    if args.quick:
        print("\n2 - compression lossless\n  [note] skipped (--quick)")
        rep.skipped_pixels = True
        rep.note("pixel comparison skipped - compression not verified against the originals")
    else:
        stage_pixels(rep, flash_dir, share_dir, len(dst or {}))
    entries = stage_reports(rep, protocol, share_dir, report_dir)
    if entries:
        stage_rdf(
            rep,
            protocol,
            entries,
            os.path.join(repo, "to_ingest", "arche.ttl"),
            os.path.join(repo, "arche", "arche_top_col.ttl"),
            os.path.join(repo, "arche", "arche_constants.ttl"),
        )
    stage_git(rep, protocol, repo)

    print()
    if rep.failures:
        print("=" * 70)
        print(f"!!!  {len(rep.failures)} CHECK(S) FAILED for {protocol}  !!!")
        for failure in rep.failures:
            print(f"  - {failure}")
        print("=" * 70)
        return 1
    for note in rep.notes:
        print(f"note: {note}")
    caveat = " (pixel comparison skipped)" if rep.skipped_pixels else ""
    if rep.pending:
        print(f"All perfect for {protocol}{caveat}, commit and proceed to next protocol.")
    else:
        print(f"All perfect for {protocol}{caveat}, proceed to next protocol.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
