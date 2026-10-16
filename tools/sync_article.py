#!/usr/bin/env python3
"""Keep version-neutral excerpts and Mermaid synchronized with companion files."""
import argparse
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
article = root / "article.md"
original = article.read_text()
# A snippet may name a region: <!-- snippet:fleet#providers --> embeds only the lines between
# "// region: providers" and "// endregion" in code/fleet.java. Interleaving regions with prose
# beats dumping a 700-line file into the middle of an article, and the excerpt still cannot drift
# from the source because it is read from it on every sync.
pattern = re.compile(
    # The region group matches empty rather than being optional: an optional group that does not
    # participate makes the \3 backreference in the end marker unmatchable, so an existing block is
    # never consumed and every run appends another copy of it.
    r"<!-- (snippet|diagram):([a-z-]+)(#[a-z-]+|) -->(?:\n.*?<!-- end:\1:\2\3 -->)?", re.S)


def region_of(source, name, region):
    begin = f"// region: {region}"
    lines = source.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == begin)
    except StopIteration:
        raise SystemExit(f"code/{name}.java has no region '{region}'")
    depth = 0
    body = []
    for line in lines[start + 1:]:
        if line.strip().startswith("// region: "):
            depth += 1
        if line.strip() == "// endregion":
            if depth == 0:
                # Regions are written at one indent inside the class; strip it uniformly so the
                # excerpt reads as a block rather than as a fragment hanging off a margin.
                margin = min((len(l) - len(l.lstrip()) for l in body if l.strip()), default=0)
                return "\n".join(l[margin:] if l.strip() else "" for l in body).rstrip()
            depth -= 1
        body.append(line)
    raise SystemExit(f"region '{region}' in code/{name}.java is never closed")
# Alt text per diagram. A diagram that cannot be seen needs a sentence, not a filename, and the
# PNG is what readers get wherever Mermaid is not rendered.
CAPTIONS = {
    "stack": "Vectors supplies SIMD math and vector collections; Models builds inference on it; "
             "ModelJars adds pinned identity and qualification; models-router takes the classifier "
             "index from Vectors and chat types from Models, and ModelJars registers a catalog "
             "provider into it; applications and the CLI sit on top",
    "loading": "Opening a model: resolve the coordinate, verify the artifact digest, map the "
               "weights, initialise the tokenizer, then build the model graph",
    "native-boundary": "Where Java calls the native kernels: the graph and session state stay in "
                       "Java while matmul and activation kernels cross the FFM boundary",
    "rag": "Retrieval-augmented generation: embed the question, search the collection, ground the "
           "prompt in the retrieved documents, then generate or abstain",
}


def expand(match):
    kind, name, region = match.group(1, 2, 3)
    region = region[1:] if region else None
    directory, extension, language = (("code", ".java", "java") if kind == "snippet"
                                       else ("diagrams", ".mmd", "mermaid"))
    source = (root / directory / (name + extension)).read_text().rstrip()
    if region:
        source = region_of(source, name, region)
    if kind == "snippet":
        # Executable companion files retain tested pins; the article shows application code.
        source = "\n".join(line for line in source.splitlines()
                           if not line.startswith(("//JAVA ", "//DEPS ")))
        source = re.sub(r"(org\.modeljars\.huggingface:[^:\s\"]+:)[^\s\"]+",
                        r"\1<model-version>", source)
        body = f"```{language}\n{source}\n```"
    else:
        # The PNG leads, because Mermaid is not rendered on every destination this article reaches.
        # The source follows so the diagram stays editable and renders live where it is supported.
        caption = CAPTIONS.get(name, name.replace("-", " "))
        for export in (f"{name}.png", f"{name}.svg"):
            if not (root / "diagrams" / export).exists():
                raise SystemExit(f"diagram {name} is missing {export}; run tools/render_diagrams.py")
        body = (f"![{caption}](diagrams/{name}.png)\n\n"
                f"<sub>[Mermaid source](diagrams/{name}.mmd) · "
                f"[SVG](diagrams/{name}.svg) · the block below is the same diagram</sub>\n\n"
                f"```{language}\n{source}\n```")
    label = f"{name}#{region}" if region else name
    return f"<!-- {kind}:{label} -->\n{body}\n<!-- end:{kind}:{label} -->"
updated = pattern.sub(expand, original)
# Every embedded snippet must resolve to a real file, so an excerpt cannot drift from its source.
# A script may be linked rather than embedded: the article carries a table of the walkthrough, and
# requiring all fourteen inline is what made the earlier draft unreadable. Unembedded scripts are
# reported so they cannot be silently orphaned instead.
snippet_names = re.findall(r"<!-- snippet:([a-z-]+)(?:#[a-z-]+)? -->", updated)
for name in snippet_names:
    if not (root / "code" / (name + ".java")).exists():
        raise SystemExit(f"article embeds code/{name}.java, which does not exist")
linked = {path.stem for path in (root / "code").glob("*.java")} - set(snippet_names)
unreferenced = sorted(name for name in linked if f"code/{name}.java" not in updated)
if unreferenced:
    raise SystemExit("scripts neither embedded nor linked: " + ", ".join(unreferenced))
diagram_names = re.findall(r"<!-- diagram:([a-z-]+) -->", updated)
assert sorted(diagram_names) == sorted(path.stem for path in (root / "diagrams").glob("*.mmd"))
if args.check:
    if updated != original:
        raise SystemExit("Article snippets differ; run tools/sync_article.py")
    print(f"PASS: all version-neutral excerpts and {len(diagram_names)} Mermaid diagrams match their source")
else:
    article.write_text(updated)
