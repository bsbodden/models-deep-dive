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

As of 15 October 2026 the published catalog has **103 entries** drawn from **67 upstream
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

That license column matters more than it looks. Three entries carry single-model terms —
`LicenseRef-Mistral-Research`, `LicenseRef-DeepSeek` and `fair-noncommercial-research-license` —
and the last of those is non-commercial on its face. Fifteen more sit under Gemma (6), Llama-3.2 (5) or
LFM-1.0 (4) terms rather than a plain OSI license. The catalog records the license per entry, so this
is a query rather than an archaeology project.

Qualification is tracked per entry and per task, not as a single badge: 65 entries carry RAG
qualifications, 31 carry embedding qualifications, 29 have a performance profile measured on
specific hardware, 3 carry tool qualifications and 2 carry speech. An entry with no profile for
your machine says so rather than guessing.

### The models people actually pull

Popularity is not something the catalog invents; it comes from upstream. These are the catalog's
busiest upstream repositories by HuggingFace 30-day downloads, read from the HuggingFace API on
15 October 2026. Across the 64 repositories that report counts, the total is 15,143,513 downloads
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
client type on purpose: one fleet can hold an in-process Models runtime, a Spring AI model and a
private gateway client without any of their SDKs reaching into `models-router`.

## One fleet, four local families, one remote provider

Here is the whole thing. Four local model families, one remote provider, a local classifier, a
retrieval arm, a decision arm, and a ledger that counts what left the machine.

<!-- snippet:fleet -->
```java
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx6g
// Four models stay resident, and each native runtime otherwise sizes its persistent worker pool
// for every logical CPU. Four pools of twelve on twelve cores is oversubscription, and it cost
// 20x: qwen3-0.6b answered the same prompt in 1,169 ms alone and 23,946 ms beside the others.
// Three threads each shares the twelve this host has.
//RUNTIME_OPTIONS -Dmodels.native.kernels.threads=3

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.integrallis.models.api.EmbeddingBackend;
import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.decisions.Verdict;
import com.integrallis.models.router.*;
import com.integrallis.models.runtime.chat.ChatMessage;
import com.integrallis.vectors.core.Document;
import com.integrallis.vectors.core.SimilarityFunction;
import com.integrallis.vectors.db.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJarDecisionRuntime;
import org.modeljars.ModelJarRuntime;
import org.modeljars.ModelJars;
import org.modeljars.composite.harriet.Harriet;

/**
 * One fleet, four local model families, one remote provider, one token ledger.
 *
 * <p>Capabilities are declarations by the operator: a model is eligible only if it claims the
 * capability a request requires. That is what keeps a heartbeat off a frontier model and sends
 * genuine synthesis to one, with no hand-written if-chain over prompt text.
 */
class fleet {
  // Declared contract prices, not measurements. Set these to your own agreement.
  static final double REMOTE_INPUT_PER_M = 1.25;
  static final double REMOTE_OUTPUT_PER_M = 10.00;
  static final String REMOTE_MODEL = "gpt-5.1";
  static final int REMOTE_OUTPUT_CAP = 2048;

  static final String EMBEDDER =
      "org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:<model-version>";
  static final String TINY =
      "org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:<model-version>";
  static final String SMALL =
      "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:<model-version>";
  static final String GROUNDER =
      "org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:<model-version>";

  /** A fleet client is whatever the application can call. Here: text in, text out. */
  interface Responder {
    String respond(String prompt) throws Exception;
  }

  static final Map<String, Object> OPEN = new LinkedHashMap<>();

  /** Provider-reported usage for the last remote call, which beats any local estimate. */
  static RoutingUsage lastRemoteUsage;

  /** One running transcript per session, which is what makes "tell me more" answerable. */
  static final List<ChatMessage> TRANSCRIPT =
      new ArrayList<>(
          List.of(
              ChatMessage.system(
                  "You are a terse support assistant for an online store. Answer the customer in"
                      + " one or two sentences, and never invent policy details.")));
  static final List<String> NOTES =
      List.of(
          "Refunds are issued to the original payment method within five business days.",
          "A duplicate charge is reversed automatically once billing reconciliation runs nightly.",
          "Account closures require written confirmation from the account holder.");

  public static void main(String... args) throws Exception {
    quietLibraries();
    var embedding = ModelJars.openEmbedding(EMBEDDER);
    OPEN.put(EMBEDDER, embedding);

    // The shipped task index was built with this same embedding model, already in the cache, so
    // classification is one local forward pass and no prompt text leaves the machine to be routed.
    var index = TaskIndexResource.openBundled();
    var classifier =
        TaskClassifier.local(PretrainedTaskClassifier.using(index, embedding::embed, 0.60));
    System.out.printf(
        "classifier: %d tasks from %s, %d-dimensional, similarity floor 0.60%n",
        index.taskNames().size(), index.embeddingModelId(), index.dimension());

    // "all-remote" measures the counterfactual the ledger cannot compute: what the same workload
    // costs when every prompt goes to the provider. Output tokens for prompts that never ran there
    // are not knowable from a local tokenizer, so they are billed by asking.
    if (args.length > 0 && "all-remote".equals(args[0])) {
      allRemote();
      return;
    }

    var retrieval = buildRetrieval(embedding);
    var fleet = buildFleet(classifier, retrieval);
    var tokenizer = runtime(SMALL).pipeline().tokenizer();

    var budget = new RoutingBudget(new BigDecimal("0.05"));
    var options =
        RoutingExecutionOptions.builder()
            .sharedBudget(budget)
            // A budget is only enforceable against a declared per-attempt ceiling, and the
            // ceiling has to be one the provider can actually honour: a reasoning model bills
            // its reasoning tokens as completion, so a 512-token output bound trips on the
            // first real call. The request below asks for the matching cap.
            .tokenBounds(new RoutingTokenBounds(4096, REMOTE_OUTPUT_CAP))
            .timeout(Duration.ofMinutes(3))
            .build();

    long remoteTokens = 0;
    long allTokens = 0;
    long localCompletionTokens = 0;
    // Cold load dominates a first call -- Harriet maps 2.7 GB -- so the local arms are opened and
    // exercised once before anything is timed. Otherwise every per-call figure below would be
    // reporting a one-off startup cost as if it were routing latency. The remote arm is not warmed,
    // because warming it would cost money for no local benefit.
    System.out.printf("%n%-20s %9s%n", "WARMING", "LOAD MS");
    long warmTotal = 0;
    var warmers = new LinkedHashMap<String, Responder>();
    warmers.put("smollm2-360m", text -> acknowledge(TINY, text));
    warmers.put("qwen3-0.6b", text -> complete(SMALL, List.of(ChatMessage.user(text)), 8));
    warmers.put("llama-3.2-1b", text -> complete(GROUNDER, List.of(ChatMessage.user(text)), 8));
    // A lambda, not a method reference: the local fleet variable shadows this class's own name.
    warmers.put("harriet-decisions", text -> decide(text));
    for (var warm : warmers.entrySet()) {
      long began = System.nanoTime();
      warm.getValue().respond("ready?");
      long millis = (System.nanoTime() - began) / 1_000_000;
      warmTotal += millis;
      System.out.printf("%-20s %9d%n", warm.getKey(), millis);
    }
    System.out.printf("%-20s %9d%n", "total", warmTotal);

    long remoteCompletionTokens = 0;
    long localRulerRemote = 0;
    // Per-model timing comes from the router's own RoutingAttempt, not a stopwatch wrapped round
    // the call, so it measures what the router measured.
    var callMillis = new LinkedHashMap<String, List<Long>>();
    long sessionStart = System.nanoTime();
    TRANSCRIPT.subList(1, TRANSCRIPT.size()).clear();
    int escalated = 0;
    var work = prompts();
    System.out.printf(
        "%n%-42s %-13s %-18s %4s %7s%n", "PROMPT", "CLASSIFIED", "SELECTED", "TOK", "MS");
    for (var prompt : work) {
      lastRemoteUsage = null;
      int tokens = tokenizer.encode(prompt.text()).length;
      allTokens += tokens;
      // A session makes the router sticky: it adds a switch margin so a conversation does not
      // hop between models on a tie. Liveness checks are not conversation turns, so they carry
      // no session and cannot anchor the session to the smallest model.
      var builder = RoutingRequest.builder(prompt.text()).estimatedTokens(tokens);
      if (prompt.session() != null) builder.sessionId(prompt.session());
      var request = builder.build();
      RoutedResult<String> result;
      try {
        result =
            fleet.execute(
                request,
                prompt.requirements(),
                RoutingContinuity.none(),
                options,
                client -> client.respond(prompt.text()),
                answer ->
                    lastRemoteUsage != null
                        ? lastRemoteUsage
                        : new RoutingUsage(tokens, estimateOutputTokens(answer)));
      } catch (RoutingBudgetExceededException denied) {
        // Reported, not fatal: one refused attempt should not discard the rest of the ledger.
        System.out.printf(
            "%-44s %-14s %-18s %d%n", abbreviate(prompt.text(), 42), "-", "refused", tokens);
        System.out.printf("    refused: %s%n", denied.getMessage());
        continue;
      }
      var chosen = result.decision().selected();
      if (chosen.local()) {
        localCompletionTokens += tokenizer.encode(String.valueOf(result.value())).length;
      } else {
        // The provider's own count supersedes the local tokenizer for the arm it bills, and the
        // local count is kept beside it so the share stays measured on one ruler.
        localRulerRemote += tokens;
        remoteTokens += lastRemoteUsage != null ? lastRemoteUsage.inputTokens() : tokens;
        remoteCompletionTokens += lastRemoteUsage != null ? lastRemoteUsage.outputTokens() : 0;
        escalated++;
      }
      long millis =
          result.attempts().isEmpty()
              ? 0
              : result.attempts().getLast().duration().toMillis();
      callMillis.computeIfAbsent(chosen.id(), key -> new ArrayList<>()).add(millis);
      System.out.printf(
          "%-42s %-13s %-18s %4d %7d%n",
          abbreviate(prompt.text(), 40),
          Objects.toString(result.decision().taskType(), "-"),
          chosen.id(),
          tokens,
          millis);
      System.out.printf("    %s%n", abbreviate(String.valueOf(result.value()), 132));
      // Pass "explain" to see why: the score breakdown names every term, including the
      // switch-margin a session grants the incumbent model.
      if (args.length > 0 && "explain".equals(args[0])) {
        System.out.printf("    %s%n", result.decision().explain().replace("\n", " | "));
      }
    }

    long sessionMillis = (System.nanoTime() - sessionStart) / 1_000_000;

    System.out.printf("%n== timing, warm ==%n");
    System.out.printf("%-20s %5s %9s %9s %9s%n", "MODEL", "CALLS", "TOTAL MS", "MEAN MS", "SHARE");
    for (var entry : callMillis.entrySet()) {
      long total = entry.getValue().stream().mapToLong(Long::longValue).sum();
      System.out.printf(
          "%-20s %5d %9d %9d %8.1f%%%n",
          entry.getKey(),
          entry.getValue().size(),
          total,
          total / entry.getValue().size(),
          100.0 * total / sessionMillis);
    }
    long accounted =
        callMillis.values().stream()
            .flatMap(List::stream)
            .mapToLong(Long::longValue)
            .sum();
    System.out.printf(
        "conversation wall clock: %d ms, of which %d ms (%.1f%%) was model calls%n",
        sessionMillis, accounted, 100.0 * accounted / sessionMillis);
    System.out.printf(
        "one-off load of the four local models: %d ms, paid once at startup, not per request%n",
        warmTotal);

    System.out.printf("%n== ledger ==%n");
    System.out.printf(
        "%d prompts, %d escalated to %s, %d answered on local weights%n",
        work.size(), escalated, REMOTE_MODEL, work.size() - escalated);

    // Two rulers, kept apart on purpose. The local tokenizer measures every prompt the same way,
    // which is what makes the share comparable; the provider's own count is what it bills.
    System.out.printf(
        "local ruler (qwen3-0.6b tokenizer): %d of %d input tokens were routed off this machine"
            + " (%.1f%%)%n",
        localRulerRemote, allTokens, 100.0 * localRulerRemote / allTokens);
    System.out.printf(
        "provider ruler (%s reported): %d input + %d completion tokens billed%n",
        REMOTE_MODEL, remoteTokens, remoteCompletionTokens);
    System.out.printf(
        "  the same prompt measured %d tokens locally, so the two rulers differ by %d%n",
        localRulerRemote, remoteTokens - localRulerRemote);
    System.out.printf("completions generated on local weights: %d tokens%n", localCompletionTokens);
    System.out.printf(
        "at the declared $%.2f/M in, $%.2f/M out: $%.6f for the one escalation; every input"
            + " remote would be $%.6f, and the local completions would have added $%.6f%n",
        REMOTE_INPUT_PER_M,
        REMOTE_OUTPUT_PER_M,
        (REMOTE_INPUT_PER_M * remoteTokens + REMOTE_OUTPUT_PER_M * remoteCompletionTokens)
            / 1_000_000.0,
        REMOTE_INPUT_PER_M * allTokens / 1_000_000.0,
        REMOTE_OUTPUT_PER_M * localCompletionTokens / 1_000_000.0);
    System.out.printf(
        "router-accounted spend: $%s of the $0.05 shared budget%n",
        budget.snapshot().spent().setScale(6, RoundingMode.HALF_UP).toPlainString());

    for (var open : OPEN.values()) {
      if (open instanceof AutoCloseable closeable) closeable.close();
    }
    retrieval.close();
    index.close();
  }

  /**
   * Four local families and one remote provider.
   *
   * <p>Only the remote candidate claims {@code reasoning}; only the grounder claims {@code
   * grounding}; only Harriet claims {@code decision}. The capability filter therefore settles
   * eligibility before any score is compared.
   */
  static ModelFleet<Responder> buildFleet(TaskClassifier classifier, VectorCollection retrieval) {
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
    var remote =
        ModelCandidate.builder(REMOTE_MODEL)
            .local(false)
            .capabilities(Set.of("chat", "reasoning", "summarization"))
            .costPerMillionTokens(REMOTE_INPUT_PER_M, REMOTE_OUTPUT_PER_M)
            .contextWindow(400000)
            .timeToFirstTokenMillis(850)
            .tokensPerSecond(90)
            .quality(Map.of("chat", 0.95, "reasoning", 0.96, "summarization", 0.94))
            .build();

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
        .model(remote, fleet::callRemote)
        .build();
  }

  record Prompt(String text, RoutingRequirements requirements, String session) {}

  /** One support session: liveness, follow-ups, closed decisions, grounded questions, synthesis. */
  static List<Prompt> prompts() {
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
    return List.of(
        new Prompt("ping", liveness, null),
        new Prompt("still there?", liveness, null),
        new Prompt("ok", liveness, null),
        new Prompt("I was charged twice for my September order.", chatHere, "s-1"),
        new Prompt("tell me more", chatHere, "s-1"),
        new Prompt(
            "I was charged twice for my September subscription and no refund arrived.",
            decision,
            null),
        new Prompt("When is a refund issued, and to which payment method?", grounded, "s-1"),
        new Prompt("What happens to a duplicate charge?", grounded, "s-1"),
        new Prompt(
            "Our refund policy promises five business days to the original payment method, while"
                + " duplicate charges reverse automatically on the nightly reconciliation. Those"
                + " two paths can disagree for a customer who is both refunded and reconciled."
                + " Work out where they conflict and draft the terms-of-service paragraph that"
                + " resolves it.",
            synthesis,
            "s-1"));
  }

  /** Sends every prompt to the provider and totals its own reported usage. */
  static void allRemote() throws Exception {
    long input = 0;
    long output = 0;
    System.out.printf("%n%-46s %8s %11s%n", "PROMPT", "IN", "COMPLETION");
    for (var prompt : prompts()) {
      lastRemoteUsage = null;
      var answer = callRemote(prompt.text());
      if (lastRemoteUsage == null) {
        System.out.printf("%-46s   no usage reported: %s%n", abbreviate(prompt.text(), 44), answer);
        continue;
      }
      input += lastRemoteUsage.inputTokens();
      output += lastRemoteUsage.outputTokens();
      System.out.printf(
          "%-46s %8d %11d%n",
          abbreviate(prompt.text(), 44),
          lastRemoteUsage.inputTokens(),
          lastRemoteUsage.outputTokens());
    }
    double cost =
        (REMOTE_INPUT_PER_M * input + REMOTE_OUTPUT_PER_M * output) / 1_000_000.0;
    System.out.printf("%n== every prompt through %s ==%n", REMOTE_MODEL);
    System.out.printf("provider-reported: %d input + %d completion tokens%n", input, output);
    System.out.printf(
        "at the declared $%.2f/M in, $%.2f/M out: $%.6f%n",
        REMOTE_INPUT_PER_M, REMOTE_OUTPUT_PER_M, cost);
    System.out.println(
        "Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a");
    System.out.println("real all-remote implementation would have to include in the input.");
  }

  // ---- arms -------------------------------------------------------------------------------

  /**
   * A liveness check is not a conversation turn: it is answered statelessly and never enters the
   * transcript, so it cannot teach the conversational model to answer everything with an
   * acknowledgement.
   */
  static String acknowledge(String coordinate, String prompt) {
    return complete(
        coordinate,
        List.of(
            ChatMessage.system(
                "You answer liveness checks. Whatever the message says, reply with exactly:"
                    + " still here."),
            ChatMessage.user("ping"),
            ChatMessage.assistant("still here"),
            ChatMessage.user(prompt)),
        8);
  }

  /** Single-shot: used by the grounded arm, which supplies its own retrieved context. */
  static String generate(String coordinate, String prompt, int maxTokens) {
    return complete(coordinate, List.of(ChatMessage.user(prompt)), maxTokens);
  }

  /** Conversational: appends to the session transcript so follow-ups resolve against it. */
  static String chat(String coordinate, String prompt, int maxTokens) {
    TRANSCRIPT.add(ChatMessage.user(prompt));
    var answer = complete(coordinate, List.copyOf(TRANSCRIPT), maxTokens);
    TRANSCRIPT.add(ChatMessage.assistant(answer));
    return answer;
  }

  static String complete(String coordinate, List<ChatMessage> messages, int maxTokens) {
    var runtime = runtime(coordinate);
    var rendered = runtime.chatTemplate().render(messages);
    return runtime
        .pipeline()
        .generate(rendered, SamplingOptions.builder().temperature(0).maxTokens(maxTokens).build())
        .strip();
  }

  /** Retrieval plus a small local model: the ordinary RAG shape, reachable only via "grounding". */
  static String ground(VectorCollection retrieval, String prompt) {
    var embedding = (EmbeddingBackend) OPEN.get(EMBEDDER);
    var hits = retrieval.search(SearchRequest.builder(embedding.embed(prompt), 2).build()).hits();
    var context = new StringBuilder();
    for (var hit : hits) context.append(hit.document().text()).append(' ');
    return generate(
        GROUNDER,
        "Notes: "
            + context.toString().strip()
            + "\nUsing only those notes, answer in one sentence. If they do not contain the"
            + " answer, say that you do not know.\nQuestion: "
            + prompt,
        64);
  }

  /** Closed answer spaces: one forward pass, no generated prose to parse or repair. */
  static String decide(String evidence) {
    var harriet = (ModelJarDecisionRuntime) OPEN.computeIfAbsent("harriet", key -> Harriet.open());
    // Each outcome carries a written rule. The Harriet javadoc records the difference this
    // makes: accuracy 0.8917 with a rubric against 0.7500 without, measured 2026-09-24 over
    // 120 JevBench items on the same model and kernel. Without one, the boolean below returns
    // a 0.50 coin flip on evidence a human reads instantly.
    var billing =
        Harriet.noul(
            harriet,
            "This ticket is about billing.",
            "the customer describes a charge, a refund, an invoice or a subscription payment",
            "the customer describes delivery, product faults, accounts or anything not monetary",
            evidence);
    var queue =
        Harriet.choice(
            harriet,
            "Which queue should handle this ticket?",
            List.of("billing", "technical", "shipping"),
            Map.of(
                "billing", "charges, refunds, invoices and subscription payments",
                "technical", "errors, outages and product faults",
                "shipping", "delivery, tracking and returns in transit"),
            evidence);
    var urgency =
        Harriet.score(
            harriet,
            "How urgent is this ticket?",
            List.of("can wait", "this week", "today"),
            Map.of(
                "can wait", "no money is at stake and nothing is blocked",
                "this week", "money is at stake but the customer is not blocked",
                "today", "the customer is blocked or out of pocket with no path forward"),
            evidence);
    return "billing=%s queue=%s urgency=%s".formatted(show(billing), show(queue), show(urgency));
  }

  static String show(Verdict verdict) {
    return "%s(p=%.2f,c=%.2f)"
        .formatted(verdict.winner(), verdict.probabilityOf(verdict.winner()), verdict.confidence());
  }

  /** The only arm that leaves the machine, reached only when a request requires reasoning. */
  static String callRemote(String prompt) throws Exception {
    var key = System.getenv("OPENAI_API_KEY");
    if (key == null || key.isBlank()) {
      return "[routed to " + REMOTE_MODEL + "; not executed because OPENAI_API_KEY is unset]";
    }
    var mapper = new ObjectMapper();
    var message = mapper.createObjectNode().put("role", "user").put("content", prompt);
    var body =
        mapper
            .createObjectNode()
            .put("model", REMOTE_MODEL)
            .put("max_completion_tokens", REMOTE_OUTPUT_CAP)
            .set("messages", mapper.createArrayNode().add(message));
    var request =
        HttpRequest.newBuilder(URI.create("https://api.openai.com/v1/chat/completions"))
            .header("Authorization", "Bearer " + key)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofMinutes(2))
            .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
            .build();
    var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
    JsonNode parsed = mapper.readTree(response.body());
    if (response.statusCode() != 200) {
      // Surfaced rather than swallowed: an empty completion would otherwise look like a short
      // answer and quietly enter the ledger as one.
      return "[%s returned HTTP %d: %s]"
          .formatted(
              REMOTE_MODEL,
              response.statusCode(),
              parsed.path("error").path("message").asText(response.body()));
    }
    var usage = parsed.path("usage");
    if (usage.hasNonNull("prompt_tokens")) {
      lastRemoteUsage =
          new RoutingUsage(usage.path("prompt_tokens").asLong(), usage.path("completion_tokens").asLong());
    }
    return parsed.path("choices").path(0).path("message").path("content").asText("");
  }

  // ---- helpers ----------------------------------------------------------------------------

  static ModelJarRuntime runtime(String coordinate) {
    return (ModelJarRuntime) OPEN.computeIfAbsent(coordinate, ModelJars::openRuntime);
  }

  static VectorCollection buildRetrieval(EmbeddingBackend embedding) {
    var probe = embedding.embed(NOTES.get(0));
    var collection =
        VectorCollection.builder()
            .dimension(probe.length)
            .metric(SimilarityFunction.COSINE)
            .indexType(IndexType.FLAT)
            .build();
    for (int i = 0; i < NOTES.size(); i++) {
      collection.add(
          new Document("note-" + i, embedding.embed(NOTES.get(i)), NOTES.get(i), Map.of()));
    }
    collection.commit();
    return collection;
  }

  /** Four characters per token is a declared estimate, used only to charge the budget. */
  static long estimateOutputTokens(String answer) {
    return answer == null ? 0 : Math.max(1, answer.length() / 4);
  }

  static String abbreviate(String text, int limit) {
    var flat = text.replaceAll("\\s+", " ").strip();
    return flat.length() <= limit ? flat : flat.substring(0, limit - 1) + "…";
  }

  static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
```
<!-- end:snippet:fleet -->

Run it and the routing table is the output:

```
WARMING                LOAD MS
smollm2-360m              2150
qwen3-0.6b                2155
llama-3.2-1b              3147
harriet-decisions        20062
total                    27514

PROMPT                                     CLASSIFIED    SELECTED            TOK      MS
ping                                       -             smollm2-360m          1     162
    still here
still there?                               -             smollm2-360m          3     167
    still here
ok                                         -             smollm2-360m          1     147
    still here
I was charged twice for my September or…   -             qwen3-0.6b            9    4040
    We'll check the details of your order to confirm if there was any issue with the payment. Let me know how we can assist you.
tell me more                               summarization qwen3-0.6b            3    2346
    Of course, let me know how we can assist you with the next steps.
I was charged twice for my September su…   -             harriet-decisions    13   12458
    billing=true(p=0.91,c=0.58) queue=billing(p=0.99,c=0.95) urgency=this week(p=0.38,c=0.01)
When is a refund issued, and to which p…   -             llama-3.2-1b         12    2081
    A refund is issued to the original payment method within five business days.
What happens to a duplicate charge?        -             llama-3.2-1b          7    1744
    A duplicate charge is reversed automatically once billing reconciliation runs nightly.
Our refund policy promises five busines…   -             gpt-5.1              55    6353
    Here’s the conflict and a clean way to resolve it in your terms. ### Where they conflict You have two different mechanisms affectin…
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

**The synthesis prompt** requires `reasoning`, which only the remote candidate declares, so it is
the one request that leaves the machine. It did leave: the answer in that last row is gpt-5.1's,
and the tokens it reports are what the ledger below bills.

<!-- diagram:rag -->
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

The router times every attempt it makes, so the conversation reports its own latency:

```
== timing, warm ==
MODEL                CALLS  TOTAL MS   MEAN MS     SHARE
smollm2-360m             3       476       158      1.5%
qwen3-0.6b               2      6386      3193     20.4%
harriet-decisions        1     12458     12458     39.8%
llama-3.2-1b             2      3825      1912     12.2%
gpt-5.1                  1      6353      6353     20.3%
conversation wall clock: 31329 ms, of which 29498 ms (94.2%) was model calls
one-off load of the four local models: 27514 ms, paid once at startup, not per request
```

A liveness check comes back in **158 ms**; the remote call takes **6,353 ms**, forty times longer.
Between them sit the conversational model at 3.2 seconds and the grounded arm, retrieval included,
at 1.9. Harriet is the slowest local arm at 12.5 seconds, because three calibrated verdicts are
three forward passes through a 4B model — it buys typed, calibrated answers rather than speed.

The 27.5 seconds of loading above the table is paid once. Four models stay resident for the whole
conversation, which is what a server does, and that resident fleet needs one explicit decision:
each native runtime sizes its worker pool for every logical CPU, so four pools on twelve cores
oversubscribe badly. The same prompt that qwen3-0.6b answers in 1,169 ms alone took 23,946 ms
beside the others until the script gave each runtime three threads. That one line is the difference
between a 31-second conversation and a 75-second one.

## What it cost

```
== ledger ==
9 prompts, 1 escalated to gpt-5.1, 8 answered on local weights
local ruler (qwen3-0.6b tokenizer): 55 of 104 input tokens were routed off this machine (52.9%)
provider ruler (gpt-5.1 reported): 61 input + 585 completion tokens billed
  the same prompt measured 55 tokens locally, so the two rulers differ by 6
completions generated on local weights: 123 tokens
at the declared $1.25/M in, $10.00/M out: $0.005926 for the one escalation; every input remote would be $0.000130, and the local completions would have added $0.001230
router-accounted spend: $0.005926 of the $0.05 shared budget
```

Eight of nine requests were answered by weights already on disk. The ninth — a genuine conflict
between two written policies — went to gpt-5.1 and billed 61 input and 585 completion tokens, which
at the script's contract prices of $1.25 and $10.00 per million comes to $0.005926. The router's own
accounting agrees to the last digit.

Measured on input tokens alone, routing looks like a coin flip: 55 of 104 left the machine. That
number is true and nearly useless, which took a second measurement to establish. The script's
`all-remote` mode sends the same nine prompts to the provider and totals what it reports:

```
PROMPT                                               IN  COMPLETION
ping                                                  7          10
still there?                                          9          22
ok                                                    7          19
I was charged twice for my September order.          15         515
tell me more                                          9         114
I was charged twice for my September subscr…         19         635
When is a refund issued, and to which payme…         18         324
What happens to a duplicate charge?                  13         380
Our refund policy promises five business da…         61         414

== every prompt through gpt-5.1 ==
provider-reported: 158 input + 2433 completion tokens
at the declared $1.25/M in, $10.00/M out: $0.024528
Floor, not a ceiling: the grounded prompts are sent without their retrieved notes, which a
real all-remote implementation would have to include in the input.
```

| | input | completion | cost |
| --- | --- | --- | --- |
| Every prompt through gpt-5.1 | 158 | 2,433 | **$0.024528** |
| As routed | 61 | 585 | **$0.005926** |

**75.8% less, a factor of 4.14.** The shape of that saving is the whole argument. The one genuinely
hard prompt accounts for 414 of the 2,433 completion tokens. The other eight account for 2,019 —
**82.8% of the entire all-remote bill**. A reasoning model spends 515 completion tokens on "I was
charged twice for my September order" and 635 on the ticket Harriet settles in three forward passes
without generating prose at all. Completion costs eight times input at these prices, and 98.7% of
the one remote call's own bill was its completion.

So the saving is not in shaving tokens off short prompts. It is in not paying a frontier model to
generate output for work that does not need generating — and in not waiting 6 seconds for an answer
a 360M model gives in 158 ms.

### Where these numbers come from

Every token count above is the provider's own report or the qwen3-0.6b tokenizer's, and the two are
kept apart because they disagree: the escalated prompt measured 55 tokens locally and 61 at the
provider. Shares are quoted on the local ruler, where every prompt is measured identically, and
bills on the provider's, where they are charged.

The prices are the script's inputs, matching published GPT-5.1 rates from third-party trackers in
September 2026; set them to your own contract. The all-remote figure is a floor, since its two
grounded prompts were sent without the retrieved notes a real implementation would have to include.
And gpt-5.1's completion count varies run to run — 383, 437, 517, 563, 585 and 611 across six runs
of the same prompt — so the table reports the run in which both arms were measured together, which
puts the ratio between 4.0 and 4.7.

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
generous for a chat reply and far too small for a model that bills its reasoning as completion. The
first keyed run stopped on `RoutingBudgetExceededException`, and the fix is to declare a ceiling the
provider was actually asked to respect. The router's part was exact: it refused the attempt, recorded
the real cost, and named the limit crossed.

**A resident fleet has to be told how to share a machine.** Four models held open, each sizing a
worker pool for all twelve cores, made qwen3-0.6b twenty times slower than it is alone. Three
threads each fixed it. This is the cost of keeping models warm, and it is worth paying — but only
once you have said how.

The run record carries all four with their numbers.

## How a model gets from a coordinate to a forward pass

Two diagrams for the parts underneath. Opening a model is resolution, verification and mapping:

<!-- diagram:loading -->
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

Every script below was repinned to ModelJars 0.1.58, Models 0.3.59 and Vectors 0.1.30 and run on
2026-10-15. All fourteen completed; outcomes are in
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
