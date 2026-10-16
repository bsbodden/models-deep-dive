# A hundred models, one dependency, and a router that keeps most of them local

ModelJars publishes language models as Maven artifacts. You add a coordinate, and the weights
arrive through the same resolver that brings you Jackson. Models is the runtime that executes them
on the JVM. This article is about what the catalog currently contains, and about the piece that
turns a pile of models into something you can actually operate: the router.

Every number below was either read from the live catalog at `modeljars.org` or printed by a script
in [`code/`](code/) on the machine named in [the run record](evidence/fleet-routing/RESULTS.md).
Two figures are not measurements and are labelled where they appear: the remote provider's prices,
which are declared inputs to the script, and the four-characters-per-token estimate the script uses
to charge its budget.

## What the catalog holds today

As of the fall of 2026 the published catalog has **103 entries** drawn from **67 upstream
repositories**, totalling 167.2 GB. The smallest is 13.7 MB and the largest 16.8 GB; the median
entry is 0.91 GB, which is the real centre of gravity — most of this catalog runs on a laptop.

Entries are not all the same kind of thing:

| Dimension | Breakdown |
| --- | --- |
| Format | 97 GGUF, 3 safetensors, 2 composite, 1 CACT |
| Capability | 67 chat and text-generation, 31 text-embedding and semantic-search, 9 code-completion, 7 reasoning, 3 tool-calling, 2 each reranking, text-to-speech and math |
| Architecture | 21 distinct families: qwen2 (21), llama (20), bert (16), qwen3 (8), qwen35 (7), nomic-bert (6), gemma3 and lfm2 (4 each), gemma4 (3), granite and soprano (2 each) |
| Quantization | 14 schemes, led by Q4_K_M (49), Q8_0 (13), Q4_0 (7) and F16 (6) |
| Domain | general (54), retrieval (34), embeddings (31), coding (10), reasoning (7), then legal, healthcare, finance, speech and mathematics in twos and threes |
| License | 77 Apache-2.0, 6 Gemma, 5 MIT, 5 Llama-3.2, 4 LFM-1.0, and 3 single-model terms including one non-commercial |

Qualification is tracked per entry and per task, not as a single badge: 65 entries carry RAG
qualifications, 31 carry embedding qualifications, 29 have a performance profile measured on
specific hardware, 3 carry tool qualifications and 2 carry speech. 

### The models people actually pull

Popularity is not something the catalog invents; it comes from upstream. These are the catalog's
busiest upstream repositories by HuggingFace 30-day downloads, read from the HuggingFace API on October 2026. Across the 64 repositories that report counts, the total is 15,143,513 downloads
in thirty days.

| Upstream repository | 30-day downloads | Catalog entry |
| --- | --- | --- |
| Qwen/Qwen2.5-0.5B-Instruct | 6,002,460 | `qwen_qwen2_5_0_5b_instruct_bf16` |
| unsloth/gemma-4-12b-it-GGUF | 1,640,046 | `unsloth_gemma_4_12b_it_gguf_q4_k_m` |
| unsloth/Qwen3.5-4B-GGUF | 1,226,766 | `unsloth_qwen3_5_4b_gguf_q4_k_m` |
| mixedbread-ai/mxbai-rerank-xsmall-v1 | 685,657 | `mixedbread_ai_mxbai_rerank_xsmall_v1_f16` |
| Qwen/Qwen3-8B-GGUF | 570,103 | `qwen3_8b_q4_k_m` |
| bartowski/Meta-Llama-3.1-8B-Instruct-GGUF | 497,742 | `llama_3_1_8b_instruct_q4_k_m` |
| ggml-org/embeddinggemma-300M-GGUF | 371,815 | `ggml_org_embeddinggemma_300m_gguf_q8_0` |
| ggml-org/gemma-4-26B-A4B-it-GGUF | 327,324 | `ggml_org_gemma_4_26b_a4b_it_gguf_q4_k_m` |

Three repositories report no download count: one upstream GGUF conversion, and the two
first-party compositions `org.modeljars.composite:harriet` and
`org.modeljars.composite:granite-answerability`, which exist only here and so have no HuggingFace
history to count. Those two are the catalog's own contributions rather than republished weights.

Note the seventh row. `embeddinggemma-300m` is a 334 MB embedding model, and it is also the model
the router's task classifier runs on — which is where this turns from a catalog into a system.

<!-- diagram:stack -->
![Vectors supplies SIMD math and vector collections; Models builds inference on it; ModelJars adds pinned identity and qualification; applications and the CLI sit on top](diagrams/stack.png)

<sub>[Mermaid source](diagrams/stack.mmd) · [SVG](diagrams/stack.svg) · the block below is the same diagram</sub>

```mermaid
flowchart BT
  V["Vectors<br/>SIMD math, quantized operations, vector collections"]
  M["Models<br/>loaders, tokenizers, model graphs, generation and task APIs"]
  J["ModelJars<br/>pinned identity, qualification, verified loading"]
  A["Your JVM application<br/>plain Java, Spring AI or LangChain4j"]
  C["modeljars.org and CLI<br/>discover, inspect, prefetch, generate examples"]
  V -->|used by| M
  M -->|used by| J
  J -->|used by| A
  C -.->|selects the same model coordinates| J
  V -->|retrieval collections| A
```
<!-- end:diagram:stack -->

## The router is part of the offering

`com.integrallis:models-router` ships a pretrained task classifier **inside the jar**: an index of
1,929 exemplar prompts across ten task types — chat, code, creative, extraction, math, reasoning,
sql, summarization, tool-use and translation — embedded at 768 dimensions with
`google_embeddinggemma_300m_gguf_q8_0` and stored SQ4-quantized. Both sides are embedded under the
prefix `task: classification | query: `, and the index records that prefix so callers do not have
to know the convention.

The consequence is that classification is one local forward pass on a model already in your cache.
No prompt text leaves the machine in order to decide where the prompt should go. That is the part
most routing layers get backwards.

Around the classifier sits the ordinary machinery, and it is worth naming precisely because each
piece earned its place in the run below:

- **Candidates** declare what they are: `capabilities`, `contextWindow`, `timeToFirstTokenMillis`,
  `tokensPerSecond`, per-task `quality`, and for remote models `costPerMillionTokens`.
- **Capabilities are a hard filter.** A model is eligible only if it declares every capability the
  request requires. This is an operator's declaration, not a measurement.
- **Policies** are weight vectors over cost, quality, latency, availability and locality.
  `BALANCED` weights quality 0.40 and latency 0.15; `LOCAL_FIRST` weights locality 0.35;
  `CHEAPEST`, `FASTEST`, `BEST_QUALITY` and `PRIVACY_STRICT` sit where their names suggest.
- **A data boundary** (`LOCAL_ONLY` or `REMOTE_ALLOWED`) is enforced per request.
- **A shared budget** charges each attempt from the candidate's declared prices against actual
  usage. When the budget denies an attempt, the router falls through to the next candidate — so an
  exhausted budget pushes work local rather than failing the request.
- **Sessions make routing sticky.** A request carrying a session id gives the incumbent model a
  `switch-margin` so a conversation does not hop between models on a near-tie.

A fleet binds candidates to whatever your application can call. `ModelFleet<T>` is generic over the
client type on purpose, and that is what makes **several remote providers ordinary rather than
special**. A provider is not a mode the router has to support; it is a candidate with its own
prices, its own context window, its own output ceiling, and a closure that knows how to call it.
One fleet can hold an in-process Models runtime, two different vendors' hosted APIs and a private
gateway, and `models-router` never learns any of their names or links any of their SDKs.

The fleet below holds three remote providers alongside the four local models: `gpt-5.1` for work
that needs reasoning, `gpt-4.1-mini` as a cheaper stablemate, and Anthropic's `claude-haiku-5-5`
through an entirely separate endpoint, credential and response shape. Only the premium one declares
`reasoning`; all three declare `long-context`. So when a request needs a long document summarised,
which provider serves it is a policy question among three, not a vendor decision written into the
code — and each client normalises its own provider's usage into one `RoutingUsage`, which is the
only thing the ledger needs.

## One fleet, seven models, three vendors

The whole program is [`code/fleet.java`](code/fleet.java), and it is worth reading in pieces rather
than at once, because each piece answers a different question.

### Declaring what the local models are for

A candidate is a description, not a wrapper. It says what the model claims to do, how fast it is,
how large a prompt it takes, and how good it is at each task. Nothing here opens a file or loads
weights.

<!-- snippet:fleet#locals -->
```java
var tiny =
    ModelCandidate.builder("smollm2-360m")
        .local(true)
        .capabilities(Set.of("chat", "liveness"))
        .contextWindow(8192)
        .timeToFirstTokenMillis(90)
        .tokensPerSecond(55)
        .quality(Map.of("chat", 0.45))
        .build();
var small =
    ModelCandidate.builder("qwen3-0.6b")
        .local(true)
        .capabilities(Set.of("chat", "summarization"))
        .contextWindow(32768)
        .timeToFirstTokenMillis(140)
        .tokensPerSecond(40)
        .quality(Map.of("chat", 0.60, "summarization", 0.62))
        .build();
var grounder =
    ModelCandidate.builder("llama-3.2-1b")
        .local(true)
        .capabilities(Set.of("chat", "grounding"))
        .contextWindow(131072)
        .timeToFirstTokenMillis(210)
        .tokensPerSecond(28)
        .quality(Map.of("chat", 0.66, "grounding", 0.70))
        .build();
var decisions =
    ModelCandidate.builder("harriet-decisions")
        .local(true)
        .capabilities(Set.of("decision"))
        .contextWindow(32768)
        .timeToFirstTokenMillis(260)
        .tokensPerSecond(1)
        .quality(Map.of("decision", 0.90))
        .build();
```
<!-- end:snippet:fleet#locals -->

The capability sets are the load-bearing part. Only SmolLM2 claims `liveness`, only the Llama arm
claims `grounding`, only Harriet claims `decision`. That is an operator's declaration about what
each model is allowed to serve, and the router treats it as a hard filter before any score is
compared — which is what keeps a liveness check off a 4B decision model without an `if` statement
anywhere.

### Declaring the remote providers

Three of them, at two vendors. They differ in price by two orders of magnitude on output.

<!-- snippet:fleet#providers -->
```java
var premium =
    ModelCandidate.builder(PREMIUM)
        .local(false)
        .capabilities(Set.of("chat", "reasoning", "summarization", "long-context"))
        .costPerMillionTokens(PREMIUM_IN, PREMIUM_OUT)
        // New in Models 0.3.60. A reasoning model bills its reasoning as completion, so it
        // cannot share an output ceiling with a model that answers a liveness check in eight
        // tokens. The execution-wide bound stays small for the local arms.
        .maxOutputTokens(PREMIUM_CAP)
        .contextWindow(400000)
        .timeToFirstTokenMillis(850)
        .tokensPerSecond(90)
        .quality(Map.of("chat", 0.95, "reasoning", 0.96, "summarization", 0.94))
        .build();
var economy =
    ModelCandidate.builder(ECONOMY)
        .local(false)
        .capabilities(Set.of("chat", "summarization", "long-context"))
        .costPerMillionTokens(ECONOMY_IN, ECONOMY_OUT)
        .maxOutputTokens(ECONOMY_CAP)
        .contextWindow(1000000)
        .timeToFirstTokenMillis(400)
        .tokensPerSecond(140)
        .quality(Map.of("chat", 0.82, "summarization", 0.86))
        .build();
var haiku =
    ModelCandidate.builder(HAIKU)
        .local(false)
        .capabilities(Set.of("chat", "summarization", "long-context"))
        .costPerMillionTokens(HAIKU_IN, HAIKU_OUT)
        .maxOutputTokens(HAIKU_CAP)
        .contextWindow(200000)
        .timeToFirstTokenMillis(300)
        .tokensPerSecond(120)
        .quality(Map.of("chat", 0.80, "summarization", 0.83))
        .build();
```
<!-- end:snippet:fleet#providers -->

Only the premium model claims `reasoning`. All three claim `long-context`, so a request to
summarise a document is settled among providers on policy rather than by a vendor name written into
the code. The `maxOutputTokens` on the premium candidate matters more than it looks: a reasoning
model bills its reasoning as completion tokens, so it cannot share an output ceiling with a model
that answers a liveness check in eight tokens.

### Binding each candidate to something callable

`ModelFleet<T>` is generic over the client type, and this is where that earns its keep. Each
provider's closure is where its SDK would live; `models-router` never learns any of their names.

<!-- snippet:fleet#wiring -->
```java
return ModelFleet.<Responder>builder()
    .classifier(classifier)
    // BALANCED weights quality at 0.40 and latency at 0.15. LOCAL_FIRST would weight
    // locality at 0.35 and latency enough that the 360M model wins ordinary chat on speed,
    // which is the wrong trade for a customer's actual question. The LOCAL_ONLY boundary on
    // those requests already keeps them on this machine, so locality needs no thumb here.
    .policy(RoutingPolicy.BALANCED)
    .model(tiny, prompt -> acknowledge(TINY, prompt))
    .model(small, prompt -> chat(SMALL, prompt, 80))
    .model(grounder, prompt -> ground(retrieval, prompt))
    .model(decisions, fleet::decide)
    // One fleet, three remote clients. Each closure is where a provider's SDK would live, so
    // models-router never learns any of their names.
    .model(premium, prompt -> callOpenAi(PREMIUM, PREMIUM_CAP, prompt))
    .model(economy, prompt -> callOpenAi(ECONOMY, ECONOMY_CAP, prompt))
    .model(haiku, prompt -> callAnthropic(HAIKU, HAIKU_CAP, prompt))
    .build();
```
<!-- end:snippet:fleet#wiring -->

Two of those closures call OpenAI with different models and ceilings. The third calls Anthropic,
which needs a different endpoint, a different auth header and a different response shape — and the
fleet does not know or care.

### Saying what each kind of traffic requires

The five requirement objects are the whole routing policy. There is no classifier branch, no
keyword matching, no prompt inspection.

<!-- snippet:fleet#requirements -->
```java
var liveness =
    RoutingRequirements.builder()
        .requireCapability("liveness")
        .dataBoundary(RoutingDataBoundary.LOCAL_ONLY)
        .build();
var chatHere =
    RoutingRequirements.builder()
        .requireCapability("chat")
        .dataBoundary(RoutingDataBoundary.LOCAL_ONLY)
        .build();
var grounded =
    RoutingRequirements.builder()
        .requireCapability("grounding")
        .dataBoundary(RoutingDataBoundary.LOCAL_ONLY)
        .build();
var decision = RoutingRequirements.builder().requireCapability("decision").build();
var synthesis = RoutingRequirements.builder().requireCapability("reasoning").build();
// No local model claims long-context, so this must go remote. Which remote is then a policy
// question among three providers rather than a vendor choice written into the code.
var longContext = RoutingRequirements.builder().requireCapability("long-context").build();
```
<!-- end:snippet:fleet#requirements -->

A liveness check wants `liveness` and must stay local. A conversation wants `chat` and must stay
local. A ticket wants `decision`. A grounded question wants `grounding` and must stay local. Only
synthesis and long-context work may leave the machine, and even then the policy picks which provider.

### Where a second vendor costs more than a config line

This is the part that only shows up when you actually call two providers:

<!-- snippet:fleet#anthropic -->
```java
static String callAnthropic(String model, int cap, String prompt) throws Exception {
  var key = System.getenv("ANTHROPIC_API_KEY");
  if (key == null || key.isBlank()) {
    return "[routed to " + model + "; not executed because ANTHROPIC_API_KEY is unset]";
  }
  var mapper = new ObjectMapper();
  var message = mapper.createObjectNode().put("role", "user").put("content", prompt);
  var body =
      mapper
          .createObjectNode()
          .put("model", model)
          .put("max_tokens", cap)
          .set("messages", mapper.createArrayNode().add(message));
  var request =
      HttpRequest.newBuilder(URI.create("https://api.anthropic.com/v1/messages"))
          .header("x-api-key", key)
          .header("anthropic-version", "2023-06-01")
          .header("Content-Type", "application/json")
          .timeout(Duration.ofMinutes(2))
          .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
          .build();
  var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
  JsonNode parsed = mapper.readTree(response.body());
  if (response.statusCode() != 200) {
    return "[%s returned HTTP %d: %s]"
        .formatted(
            model,
            response.statusCode(),
            parsed.path("error").path("message").asText(response.body()));
  }
  // Anthropic reports input_tokens and output_tokens where OpenAI reports prompt_ and
  // completion_. Each client normalises its own provider into one RoutingUsage.
  var usage = parsed.path("usage");
  if (usage.hasNonNull("input_tokens")) {
    lastRemoteUsage =
        new RoutingUsage(
            usage.path("input_tokens").asLong(), usage.path("output_tokens").asLong());
  }
  // Haiku 5.5 returns a thinking block first and the answer after it, so the text block has to
  // be found rather than assumed at index zero. Reading content[0] yields an empty answer that
  // then enters the ledger as a short one.
  for (JsonNode block : parsed.path("content")) {
    if ("text".equals(block.path("type").asText())) {
      return block.path("text").asText("");
    }
  }
  return "[%s returned no text block]".formatted(model);
}
```
<!-- end:snippet:fleet#anthropic -->

Anthropic reports `input_tokens` and `output_tokens` where OpenAI reports `prompt_tokens` and
`completion_tokens`, and it returns `content` as an array whose first block is `thinking` with the
answer in a later `text` block. Reading `content[0].text` yields an empty string, which then enters
the ledger as a short answer rather than as an error — it did exactly that on the first run. Each
client normalises its own provider into one `RoutingUsage`, and that is the only shape the ledger
needs to know.

### Counting what it cost, per provider

<!-- snippet:fleet#ledger -->
```java
if (!remoteSpend.isEmpty()) {
  System.out.printf("%-20s %8s %12s %12s%n", "REMOTE PROVIDER", "IN", "COMPLETION", "COST");
  var total = BigDecimal.ZERO;
  for (var entry : remoteSpend.entrySet()) {
    long[] t = remoteTokensBy.get(entry.getKey());
    total = total.add(entry.getValue());
    System.out.printf(
        "%-20s %8d %12d %12s%n",
        entry.getKey(),
        t[0],
        t[1],
        "$" + entry.getValue().setScale(6, RoundingMode.HALF_UP).toPlainString());
  }
  System.out.printf(
      "%-20s %8d %12d %12s%n",
      "total",
      remoteTokens,
      remoteCompletionTokens,
      "$" + total.setScale(6, RoundingMode.HALF_UP).toPlainString());
}
```
<!-- end:snippet:fleet#ledger -->

`costOf` belongs to the candidate that actually ran. With one remote provider that is a detail; with
three at different prices it is the difference between a ledger and a guess.

The rest of the file — the warm-up, the routing loop, the local arms and the timing table — is in
[`code/fleet.java`](code/fleet.java). Run it with Java 25 and JBang from [`code/`](code/README.md).

Run it and the routing table is the output:

```
WARMING                LOAD MS
smollm2-360m              2493
qwen3-0.6b                2439
llama-3.2-1b              3478
harriet-decisions        21685
total                    30095

PROMPT                                   CLASSIFIED           SELECTED            TOK      MS
ping                                     ~chat 0.48           smollm2-360m          1     169
    still here
still there?                             ~summarization 0.50  smollm2-360m          3     170
    still here
ok                                       ~reasoning 0.57      smollm2-360m          1     149
    still here
I was charged twice for my September …   ~tool-use 0.46       qwen3-0.6b            9    4288
    We'll check the details of your order to confirm if there was any issue with the payment. Let me know how we can assist you.
tell me more                             summarization        qwen3-0.6b            3    2267
    Of course, let me know how we can assist you with the next steps.
I was charged twice for my September …   ~tool-use 0.49       harriet-decisions    13   13910
    billing=true(p=0.91,c=0.58) queue=billing(p=0.99,c=0.95) urgency=this week(p=0.38,c=0.01)
When is a refund issued, and to which…   ~tool-use 0.51       llama-3.2-1b         12    2049
    A refund is issued to the original payment method within five business days.
What happens to a duplicate charge?      ~code 0.45           llama-3.2-1b          7    1716
    A duplicate charge is reversed automatically once billing reconciliation runs nightly.
Our refund policy promises five busin…   ~tool-use 0.52       gpt-5.1              55   10400
    There are two flows that can collide: 1. **Manual refund path** - You initiate a refund. - Policy promises: “Refund within five bus…
Summarise this appendix for the suppo…   ~summarization 0.54  claude-haiku-5-5     84    1131
    Refunds go to the original payment method within five business days, and duplicate charges are reversed automatically by the nightl…
```

Five kinds of traffic, five different destinations, no `if` statement over prompt text:

**Heartbeats** (`ping`, `still there?`, `ok`) require a `liveness` capability that only the 360M
SmolLM2 declares. They are answered statelessly, in 8 tokens, and never enter the conversation
transcript — because a liveness check is not a conversation turn.

**The conversation** (`I was charged twice…`, then `tell me more`) requires `chat` with a
`LOCAL_ONLY` boundary, and carries a session id. The first turn picks qwen3-0.6b on quality; the
follow-up stays there because of the switch margin. `tell me more` only means anything because the
transcript is real, which is why the arm appends both sides of each turn.

**The closed decisions** go to Harriet, which answers three typed questions in three forward
passes: a boolean, a choice over three queues, and an ordered severity. Nothing is generated, so
there is no JSON to repair. Each outcome carries a written rule, and that matters: Harriet's own
javadoc records accuracy **0.8917 with a rubric against 0.7500 without**, measured 2026-09-24 over
120 JevBench items on the same model and kernel. Note that the model is confident about what the
ticket is (`p=0.99`) and openly unconfident about its urgency (`c=0.01`) — a calibrated model
declining to commit is the feature, not a defect.

**The grounded questions** require a `grounding` capability that only the Llama-3.2-1B arm declares,
and that arm does retrieval before generation. Both answers come back as one sentence drawn from
the notes.

**The synthesis prompt** requires `reasoning`, which only `gpt-5.1` declares among the three
remotes, so it is the one request that can only go there. **The appendix summary** requires
`long-context`, which no local model claims and all three remotes do, so the policy picks among
providers — and it picked Anthropic's Haiku, the cheapest and fastest of them. Both calls really
happened: those answers are the providers', and the tokens they report are what the ledger bills.

The `CLASSIFIED` column repays a second look. Only `tell me more` clears the classifier's 0.60
similarity floor, as `summarization`. The rest print their nearest task with a tilde and the
similarity that fell short — `ping` is ~chat at 0.48, `ok` is ~reasoning at 0.57, "What happens to a
duplicate charge?" is ~code at 0.45. That is `PretrainedTaskClassifier.match`, new in Models 0.3.60.
Before it, every one of those rows was a bare dash, and a prompt unlike every exemplar looked
identical to one that nearly matched. The numbers say what is really going on: an index built from
1,929 work-shaped prompts has nothing much to say about conversational filler, and it reports that
honestly instead of guessing a task and silently applying the wrong quality column.

<!-- diagram:rag -->
![Retrieval-augmented generation: embed the question, search the collection, ground the prompt in the retrieved documents, then generate or abstain](diagrams/rag.png)

<sub>[Mermaid source](diagrams/rag.mmd) · [SVG](diagrams/rag.svg) · the block below is the same diagram</sub>

```mermaid
flowchart TD
  D["Documents"] --> E["Models embedding runtime"]
  E --> V["Vectors collection"]
  Q["Question"] --> QE["Same embedding model"]
  QE --> V
  V --> H["Retrieved text and source IDs"]
  H --> P["Grounding preflight"]
  P -->|enough evidence| G["Models generation runtime"]
  P -->|insufficient evidence| A["Abstain"]
  G --> C["Grounded answer policy"]
  C --> O["Answer plus outcome:<br/>model, abstention or extractive fallback"]
```
<!-- end:diagram:rag -->

## What it took

The router times every attempt, so the conversation reports its own latency:

```
== timing, warm ==
MODEL                CALLS  TOTAL MS   MEAN MS     SHARE
smollm2-360m             3       488       162      1.2%
qwen3-0.6b               2      6555      3277     15.9%
harriet-decisions        1     13910     13910     33.8%
llama-3.2-1b             2      3765      1882      9.1%
gpt-5.1                  1     10400     10400     25.3%
claude-haiku-5-5         1      1131      1131      2.7%
conversation wall clock: 41152 ms, of which 36249 ms (88.1%) was model calls
one-off load of the four local models: 30095 ms, paid once at startup, not per request
```

A liveness check answers in **162 ms**. Among the remotes, Anthropic's Haiku returns in **1,131 ms**
and gpt-5.1 takes **10,400 ms** — nine times longer, for the one request that genuinely needed a
reasoning model. Between them sit the grounded arm at 1.9 seconds, the conversational model at 3.3,
and Harriet at 13.9, because three calibrated verdicts are three forward passes through a 4B model.

Those shapes hold across runs on an unloaded machine; the absolute numbers do not hold on a busy
one. An earlier measurement put the conversational model at 18,753 ms, which was the laptop at load
average 20 with three and a half million pageouts, not the model.

The 30 seconds of loading above the table is paid once. Four models stay resident, which is what a
server does, and a resident fleet needs one explicit decision: each native runtime otherwise sizes
its worker pool for every logical CPU, so four pools on twelve cores oversubscribe badly. The same
prompt qwen3-0.6b answers in 1,169 ms alone took 23,946 ms beside the others until the script gave
each runtime three threads.

## What it cost

```
== ledger ==
10 prompts, 2 escalated to a remote provider, 8 answered on local weights
local ruler (qwen3-0.6b tokenizer): 139 of 188 input tokens were routed off this machine (73.9%)
provider ruler (gpt-5.1 reported): 204 input + 702 completion tokens billed
  the same prompt measured 139 tokens locally, so the two rulers differ by 65
completions generated on local weights: 123 tokens
REMOTE PROVIDER            IN   COMPLETION         COST
gpt-5.1                    61          598    $0.006056
claude-haiku-5-5          143          104    $0.000066
total                     204          702    $0.006123
had every prompt gone to gpt-5.1: $0.000235 of input alone, plus $0.001230 for the completions this machine produced for nothing
router-accounted spend: $0.006123 of the $0.05 shared budget
```

Eight of ten requests never left the machine. Of the two that did, the policy conflict went to
gpt-5.1 and the appendix summary went to Haiku, and the per-provider table is where having more than
one remote stops being a design note and starts being money: **598 completion tokens on gpt-5.1 cost
$0.006056, while 104 on Haiku cost $0.000066.** Per completion token that is $10.00 against $0.50 per
million — a factor of twenty for work that did not need the expensive one. The ledger prices each
line with `ModelCandidate.costOf` on the candidate that actually ran, which is the only way this
stays right once a fleet holds several providers, and the router's own accounted spend matches the
total exactly.

Measured on input tokens alone, routing looks unimpressive: 139 of 188 left the machine, because the
two escalated prompts are the long ones. The script's `all-remote` mode settles what that is worth
by sending the same ten prompts to gpt-5.1 and totalling what it reports:

```
PROMPT                                               IN  COMPLETION
ping                                                  7          10
still there?                                          9          22
ok                                                    7          24
I was charged twice for my September order.          15         428
tell me more                                          9         109
I was charged twice for my September subscr…         19         625
When is a refund issued, and to which payme…         18         237
What happens to a duplicate charge?                  13         400
Our refund policy promises five business da…         61         430
Summarise this appendix for the support han…         89          70

== every prompt through gpt-5.1 ==
provider-reported: 247 input + 2355 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.023859
Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a
real all-remote implementation would have to include in the input.
```

| | input | completion | cost |
| --- | --- | --- | --- |
| Every prompt through gpt-5.1 | 247 | 2,355 | **$0.023859** |
| As routed across three providers | 204 | 702 | **$0.006123** |

**74.3% less, a factor of 3.90.** The shape of it: the eight prompts that stayed local would have
billed 1,855 completion tokens on gpt-5.1, or **$0.018671 — 78.3% of the entire all-remote bill.** A
reasoning model spends 428 completion tokens on "I was charged twice for my September order" and 625
on the ticket Harriet settles in three forward passes without generating prose at all.

So the saving is not in shaving tokens off short prompts. It is in not paying a frontier model to
generate output that does not need generating, and in not sending to the expensive provider what the
cheap one answers nine times faster.

### Where these numbers come from

Token counts are each provider's own report or the qwen3-0.6b tokenizer's, kept apart because they
disagree — the escalated prompts measured 139 tokens locally and 204 at the providers. Shares are
quoted on the local ruler, where every prompt is measured identically, and bills on the provider's,
where they are charged.

Prices are the script's declared inputs, matching published rates from third-party trackers in
September and October 2026: $1.25/$10.00 per million for gpt-5.1, $0.40/$1.60 for gpt-4.1-mini, and
$0.10/$0.50 for Haiku 5.5. Set them to your own contracts. Haiku is additionally tiered — $0.50/$2.50
above a 100k-token prompt — and a candidate declares a single pair, so this fleet would misprice a
very long request to it.

The all-remote figure is a floor: its grounded prompts were sent without the retrieved notes a real
implementation would include. And completion counts are not deterministic, so the table reports the
run in which both arms were measured together rather than a best case.

## Four things only a real run would tell you

**A decision without a rubric is a coin flip.** Harriet's yes-or-no call accepts a written rule for
each outcome, and without them the question "is this ticket about billing?" came back
`false p=0.503 confidence=0.00` on evidence any human reads at a glance. With the rules attached it
returns `true p=0.920 confidence=0.60`. Harriet's javadoc puts a number on that gap — accuracy
0.8917 with a rubric against 0.7500 without, over 120 JevBench items — and this is what it looks
like from the outside.

**A heartbeat should not get a vote on the conversation.** Sessions make the router sticky on
purpose: an incumbent model gets a `switch-margin` so a conversation does not hop mid-flight. Give
every prompt the same session id and the first heartbeat anchors the whole exchange to the 360M
model, which then handles a real customer complaint badly. Liveness checks carry no session, and
`scoreBreakdown()` is what shows you why — `switch-margin=0.05`, sitting in the numbers.

**A reasoning model does not fit a chat model's output bound.** A 512-token completion ceiling is
generous for a chat reply and far too small for a model that bills its reasoning as completion, so
the first keyed run stopped on `RoutingBudgetExceededException`. The router's own part was exact: it
refused the attempt, recorded the real cost, and named the limit it crossed. What it could not do
was hold two models to two different ceilings, because the bound belonged to the execution rather
than the candidate — and worse, a bound checked after the call discarded the completion the call had
already been billed for. Models 0.3.60 fixes both: a candidate declares its own `maxOutputTokens`,
and an overrun carries `billedResult()`, `billedUsage()` and `billedCost()` so the spend buys
something. The script declares 2,048 on the remote candidate and leaves the fleet-wide bound small
for the local arms.

**A resident fleet has to be told how to share a machine.** Four models held open, each sizing a
worker pool for all twelve cores, made qwen3-0.6b twenty times slower than it is alone. Three
threads each fixed it. This is the cost of keeping models warm, and it is worth paying — but only
once you have said how.

The run record carries all four with their numbers.

## How a model gets from a coordinate to a forward pass

Two diagrams for the parts underneath. Opening a model is resolution, verification and mapping:

<!-- diagram:loading -->
![Opening a model: resolve the coordinate, verify the artifact digest, map the weights, initialise the tokenizer, then build the model graph](diagrams/loading.png)

<sub>[Mermaid source](diagrams/loading.mmd) · [SVG](diagrams/loading.svg) · the block below is the same diagram</sub>

```mermaid
sequenceDiagram
  participant App as Application
  participant MJ as ModelJars
  participant Cache as Artifact cache
  participant HF as Pinned upstream
  participant Models as Models
  App->>MJ: openRuntime(coordinate)
  MJ->>MJ: Resolve descriptor<br/>and task qualification
  MJ->>Cache: Locate artifact<br/>or bundle
  alt Files not cached
    Cache->>HF: Download declared files
    HF-->>Cache: Weights, tokenizer<br/>and configuration
  end
  MJ->>MJ: Verify sizes<br/>and SHA-256
  MJ->>Models: Load qualified execution path
  Models-->>App: Runtime and chat template
  App->>Models: Render prompt, generate
  Models-->>App: Text and metrics
  App->>Models: close()
```
<!-- end:diagram:loading -->

And the boundary between Java and the native kernels, which is where the arithmetic that matters
actually runs:

<!-- diagram:native-boundary -->
![Where Java calls the native kernels: the graph and session state stay in Java while matmul and activation kernels cross the FFM boundary](diagrams/native-boundary.png)

<sub>[Mermaid source](diagrams/native-boundary.mmd) · [SVG](diagrams/native-boundary.svg) · the block below is the same diagram</sub>

```mermaid
flowchart TD
  APP["Application task"] --> JAVA["Java: model graph, state and sampling"]
  JAVA --> V["Java and Vectors kernels"]
  JAVA --> FFM["Java FFM"]
  FFM --> CPU["Models Rust CPU kernels"]
  FFM --> DRIVER["Optional CUDA driver calls"]
  DRIVER --> PTX["Models Rust kernels compiled to PTX"]
  APP -.-> APPLE["Optional Apple integration"]
  APPLE --> SWIFT["FFM to Swift bridge"]
  SWIFT --> AFM["Apple Foundation Models"]

  CPU -. evaluate a replacement .-> J["Java candidate for one routed operation"]
  PTX -. evaluate a replacement .-> J
  J --> C{"Same numeric contract?"}
  C -->|no| KEEP["Keep current route and record evidence"]
  C -->|yes| B["Measure candidate against current route on the same host"]
  B --> G{"Kernel and whole-model gates pass?"}
  G -->|no| KEEP
  G -->|yes| P{"Supported hosts and workloads pass?"}
  P -->|no| KEEP
  P -->|yes| R["Route this operation to Java; remove unused native code"]
```
<!-- end:diagram:native-boundary -->

## The rest of the walkthrough

Every script below runs on ModelJars 0.1.59, Models 0.3.60 and Vectors 0.1.30, all released and
verified on Maven Central. All fourteen completed on 2026-10-15; outcomes are in
[the run record](evidence/fleet-routing/RESULTS.md).

| Script | What it shows |
| --- | --- |
| [`chat.java`](code/chat.java) | A GGUF chat model end to end, with load, prefill and decode timings |
| [`safetensors.java`](code/safetensors.java) | The same API over a BF16 safetensors bundle |
| [`embed.java`](code/embed.java) | A 1,024-dimensional embedding |
| [`gemma.java`](code/gemma.java) | EmbeddingGemma under the publisher's own prefix recipe |
| [`rerank.java`](code/rerank.java) | Cross-encoder reranking, correct ordering by score |
| [`rag.java`](code/rag.java) | Retrieval with a grounding policy that can abstain |
| [`tools.java`](code/tools.java) | A model proposing tool calls that the JVM executes |
| [`composite.java`](code/composite.java) | A composition sharing a physical KV prefix, 182 tokens |
| [`decisions.java`](code/decisions.java) | Typed, calibrated decisions with no generation |
| [`speech.java`](code/speech.java) | Text to a 32 kHz wav, RTF 1.433 |
| [`spring.java`](code/spring.java) | The same model behind a Spring AI `ChatModel` |
| [`route.java`](code/route.java) | Discovery over what is already cached, selection only |
| [`bonsai.java`](code/bonsai.java) | A verified 5.95 GB PTQ1_0 artifact |
| [`fleet.java`](code/fleet.java) | The routing fleet and ledger above |

Run them with Java 25 and JBang from [`code/`](code/README.md). Routing discovers only models that
are already cached, so run `chat.java` and `safetensors.java` before `route.java`.

## What this adds up to

A catalog is only interesting if you can choose from it, and choosing by hand does not scale past
about three models. The router turns 103 entries into a fleet you can state the rules for: what each
model is allowed to serve, which traffic may leave the machine, what you are willing to spend, and
how much better an alternative must be before a conversation switches models mid-flight. Then it
tells you which rule fired, in numbers, for every request.

Most of the traffic in the run above never needed a frontier model. One request did, and it got
one. That is the whole argument.
