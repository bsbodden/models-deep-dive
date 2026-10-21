# Models and ModelJars deep dive

A hundred models published as Maven artifacts, the router that chooses between them, and a runnable
fleet that keeps most of the traffic on local weights.

Start with **[the article](article.md)**. Every figure in it was read from the live catalog at
modeljars.org or printed by a script in [`code/`](code/) on the host named in
[the run record](evidence/fleet-routing/RESULTS.md).

The libraries it exercises are public: [integrallis/models](https://github.com/integrallis/models),
[integrallis/vectors](https://github.com/integrallis/vectors) and
[ModelJars/modeljars](https://github.com/ModelJars/modeljars).

- [Runnable JBang walkthrough](code/README.md)
- [Routing fleet run record and the two defects it found](evidence/fleet-routing/RESULTS.md)
- **What the fleet's quality claims rest on**, each with its protocol frozen before the data:
  [routing accuracy](experiments/routing-accuracy/README.md) (four public datasets, which rejected
  three of the fleet's four declarations),
  [grounding arm selection](experiments/grounding-arm-selection/README.md) (does a larger local
  model reach the frontier model's accuracy?) and
  [local-only chat](experiments/local-only-chat/README.md) (which local arm may serve a turn the
  data boundary forbids sending anywhere). The declarations themselves are in
  [PARITY-BASIS.json](PARITY-BASIS.json) and `make check` refuses any the measurements do not
  support.
- [Mermaid sources](diagrams/)
- [Latest model onboarding and release report](evidence/onboarding-release-report.md)
- [Initial article correction report](evidence/release-report.md)
- [Sources and validation boundaries](evidence/sources.md)
- [Released walkthrough results](evidence/walkthrough-results.md)
- [Defects found and corrected](evidence/article-findings.md)
- [Playable walkthroughs](recordings/index.html) and [recording workflow](recordings/README.md)

The Java and Mermaid files are the authoritative sources. Inline excerpts omit JDK/dependency declarations and show `<model-version>` placeholders, while the downloadable scripts retain tested pins. The synchronization tool applies that presentation rule consistently.

A script may be embedded whole with a `<!-- snippet:name -->` marker, embedded in pieces with `<!-- snippet:name#region -->`, or linked from the walkthrough table. A region is the lines between `// region: name` and `// endregion` in the Java file, re-read on every sync and dedented as a block, which is how the fleet walkthrough interleaves prose with code instead of dropping a 480-line file into the middle of the article. A marker naming a region that does not exist fails the sync rather than emitting nothing. Every embedded snippet must resolve to a real file, and every script must be either embedded or linked, so none can drift from its source or be silently orphaned. Requiring all fourteen inline is what made the earlier draft unreadable.

Each `<!-- diagram:name -->` marker expands to the PNG export first, then the Mermaid source. The PNG is what readers get wherever Mermaid is not rendered — Medium, PDF, most feed readers — and the source keeps the diagram editable and renders live on GitHub. Alt text lives in `CAPTIONS` in the sync tool, because a diagram that cannot be seen needs a sentence rather than a filename. The tool refuses to run if a diagram is missing its `.png` or `.svg`, so the article cannot ship an image reference that resolves to nothing. After changing either:

```bash
python3 tools/sync_article.py
python3 tools/sync_article.py --check
```

To check diagram syntax without adding JavaScript dependencies to the libraries:

```bash
npm install --prefix /private/tmp/models-article-mermaid --no-package-lock mermaid@11.12.0 jsdom@26.1.0
node tools/check_mermaid.mjs /private/tmp/models-article-mermaid/node_modules
```

`make check` is what CI runs, and it is four claims about this repository rather than a lint: every
scored number re-derives from the raw rows committed beside it, every figure in the article
re-derives from the archived run logs, every capability the demo fleet declares is matched to a
measurement of the model it actually ships, and the gate that does that matching has its own
twelve-case test suite — because a gate nobody tests is a gate that passes for the wrong reason,
which has already happened twice here. `make measured` runs the checks that need a JVM, the
local weights or a provider key, on a machine that has them.

The article is a local draft. Repository fixes and library publication are tracked separately
from publishing the prose. Recordings retain original terminal casts as well as edited video exports.

SVG and PNG exports sit beside each `.mmd` source. Their render hashes are recorded in
[evidence/diagram-renders.json](evidence/diagram-renders.json); the visual theme is
[diagrams/render-config.json](diagrams/render-config.json). They were rendered with
`@mermaid-js/mermaid-cli@11.12.0` and local Chrome. Keep the Mermaid source when preparing
Medium exports so later corrections remain editable.

To regenerate the diagram exports with an installed Chrome executable:

```bash
PUPPETEER_SKIP_DOWNLOAD=true npm install --prefix /private/tmp/models-article-mermaid --no-package-lock @mermaid-js/mermaid-cli@11.12.0
python3 tools/render_diagrams.py --mmdc /private/tmp/models-article-mermaid/node_modules/.bin/mmdc --chrome '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```
