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
pattern = re.compile(r"<!-- (snippet|diagram):([a-z-]+) -->(?:\n.*?<!-- end:\1:\2 -->)?", re.S)
# Alt text per diagram. A diagram that cannot be seen needs a sentence, not a filename, and the
# PNG is what readers get wherever Mermaid is not rendered.
CAPTIONS = {
    "stack": "Vectors supplies SIMD math and vector collections; Models builds inference on it; "
             "ModelJars adds pinned identity and qualification; applications and the CLI sit on top",
    "loading": "Opening a model: resolve the coordinate, verify the artifact digest, map the "
               "weights, initialise the tokenizer, then build the model graph",
    "native-boundary": "Where Java calls the native kernels: the graph and session state stay in "
                       "Java while matmul and activation kernels cross the FFM boundary",
    "rag": "Retrieval-augmented generation: embed the question, search the collection, ground the "
           "prompt in the retrieved documents, then generate or abstain",
}


def expand(match):
    kind, name = match.group(1, 2)
    directory, extension, language = (("code", ".java", "java") if kind == "snippet"
                                       else ("diagrams", ".mmd", "mermaid"))
    source = (root / directory / (name + extension)).read_text().rstrip()
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
    return f"<!-- {kind}:{name} -->\n{body}\n<!-- end:{kind}:{name} -->"
updated = pattern.sub(expand, original)
# Every embedded snippet must resolve to a real file, so an excerpt cannot drift from its source.
# A script may be linked rather than embedded: the article carries a table of the walkthrough, and
# requiring all fourteen inline is what made the earlier draft unreadable. Unembedded scripts are
# reported so they cannot be silently orphaned instead.
snippet_names = re.findall(r"<!-- snippet:([a-z-]+) -->", updated)
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
