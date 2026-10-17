//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx6g
// Four models stay resident, and each native runtime otherwise sizes its persistent worker pool
// for every logical CPU. Four pools of twelve on twelve cores is oversubscription, and it cost
// 20x: qwen3-0.6b answered the same prompt in 1,169 ms alone and 23,946 ms beside the others.
// Three threads each shares the twelve this host has.
//RUNTIME_OPTIONS -Dmodels.native.kernels.threads=3
//DEPS org.modeljars:modeljars:0.1.61
//DEPS com.integrallis:models-router:0.4.3
//DEPS com.integrallis:vectors-db:0.1.30
//DEPS com.fasterxml.jackson.core:jackson-databind:2.22.3
//DEPS org.modeljars.composite:harriet:0.1.61
//DEPS org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:3.0.0-q8_0.1
//DEPS org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:2.0.0-q8_0.1
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1
//DEPS org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1

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
  // Declared contract prices, not measurements. Set these to your own agreements.
  static final String PREMIUM = "gpt-5.1";
  static final double PREMIUM_IN = 1.25;
  static final double PREMIUM_OUT = 10.00;
  static final int PREMIUM_CAP = 2048;

  // A second provider in the same fleet, an order of magnitude cheaper on output.
  static final String ECONOMY = "gpt-4.1-mini";
  static final double ECONOMY_IN = 0.40;
  static final double ECONOMY_OUT = 1.60;
  static final int ECONOMY_CAP = 1024;

  // A third provider at a different vendor: its own endpoint, credential, auth header and JSON
  // shape. Anthropic prices Haiku 5.5 in tiers -- $0.10/$0.50 under a 100k-token prompt and
  // $0.50/$2.50 at or over it -- which Models 0.4.0 can express, so the candidate below declares
  // both rather than silently pricing a long request at the cheap one.
  static final String HAIKU = "claude-haiku-5-5";
  static final double HAIKU_IN = 0.10;
  static final double HAIKU_OUT = 0.50;
  static final double HAIKU_HIGH_IN = 0.50;
  static final double HAIKU_HIGH_OUT = 2.50;
  static final int HAIKU_CAP = 1024;

  static final String EMBEDDER =
      "org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:3.0.0-q8_0.1";
  static final String TINY =
      "org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:2.0.0-q8_0.1";
  static final String SMALL =
      "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";
  static final String GROUNDER =
      "org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1";

  // The same four models as the catalog names them. A coordinate is what you depend on; a catalog
  // id is what discovery reports and what the router then routes to, so the ledger below is keyed
  // on the second. Harriet's composite contributes its base weights under the fourth id.
  static final String TINY_ID = "smollm2_360m_instruct_q8_0";
  static final String SMALL_ID = "qwen3_0_6b_q4_0";
  static final String GROUNDER_ID = "bartowski_llama_3_2_1b_instruct_gguf_q4_k_m";
  static final String HARRIET_ID = "unsloth_qwen3_5_4b_gguf_q4_k_m";

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
    var pretrained = PretrainedTaskClassifier.using(index, embedding::embed, 0.60);
    var classifier = TaskClassifier.local(pretrained);
    System.out.printf(
        "classifier: %d tasks from %s, %d-dimensional, similarity floor 0.60%n",
        index.taskNames().size(), index.embeddingModelId(), index.dimension());

    // "all-remote" measures the counterfactual the ledger cannot compute: what the same workload
    // costs when every prompt goes to the provider. Output tokens for prompts that never ran there
    // are not knowable from a local tokenizer, so they are billed by asking.
    var retrieval = buildRetrieval(embedding);
    if (args.length > 0 && "all-remote".equals(args[0])) {
      allRemote(retrieval);
      return;
    }

    // Warmed before the fleet is built, and the order matters on a machine that has not run this
    // before. ModelJarsCatalog.discover() skips any model whose weights are not on disk -- it
    // checks the descriptor's localPath and then the content-addressed cache -- so discovery has
    // nothing to report until the weights have been fetched, and opening each runtime is what
    // fetches them. Warming is needed anyway: cold load dominates a first call, Harriet maps
    // 2.7 GB, and every per-call figure below would otherwise report a one-off startup cost as
    // routing latency. The remote arms are not warmed; that would cost money for no local benefit.
    System.out.printf("%n%-32s %9s%n", "WARMING", "LOAD MS");
    long warmTotal = 0;
    var warmers = new LinkedHashMap<String, Responder>();
    warmers.put(TINY_ID, text -> acknowledge(TINY, text));
    warmers.put(SMALL_ID, text -> complete(SMALL, List.of(ChatMessage.user(text)), 8));
    warmers.put(GROUNDER_ID, text -> complete(GROUNDER, List.of(ChatMessage.user(text)), 8));
    // A lambda, not a method reference: the local fleet variable shadows this class's own name.
    warmers.put(HARRIET_ID, text -> decide(text));
    for (var warm : warmers.entrySet()) {
      long began = System.nanoTime();
      warm.getValue().respond("ready?");
      long millis = (System.nanoTime() - began) / 1_000_000;
      warmTotal += millis;
      System.out.printf("%-32s %9d%n", abbreviate(warm.getKey(), 32), millis);
    }
    System.out.printf("%-32s %9d%n", "total", warmTotal);

    var fleet = buildFleet(classifier, retrieval);
    var tokenizer = runtime(SMALL).pipeline().tokenizer();

    var budget = new RoutingBudget(new BigDecimal("0.50"));
    var options =
        RoutingExecutionOptions.builder()
            .sharedBudget(budget)
            // Both halves are fleet-wide fallbacks sized for the local arms, because every remote
            // candidate declares its own ceiling. This pair also sets the floor on the context a
            // request must fit -- the execution takes input + output -- so making it large to
            // admit one big prompt would make every small prompt unroutable.
            .tokenBounds(new RoutingTokenBounds(4096, 512))
            .timeout(Duration.ofMinutes(3))
            .build();

    long remoteTokens = 0;
    long allTokens = 0;
    long localCompletionTokens = 0;

    long remoteCompletionTokens = 0;
    long localRulerRemote = 0;
    // Per provider, because there is more than one and they do not cost the same.
    var remoteSpend = new LinkedHashMap<String, BigDecimal>();
    var remoteTokensBy = new LinkedHashMap<String, long[]>();
    // Per-model timing comes from the router's own RoutingAttempt, not a stopwatch wrapped round
    // the call, so it measures what the router measured.
    var callMillis = new LinkedHashMap<String, List<Long>>();
    long sessionStart = System.nanoTime();
    TRANSCRIPT.subList(1, TRANSCRIPT.size()).clear();
    int escalated = 0;
    var work = prompts();
    System.out.printf(
        "%n%-32s %-20s %-32s %9s %7s%n", "PROMPT", "CLASSIFIED", "SELECTED", "LOCAL IN", "MS");
    for (var prompt : work) {
      lastRemoteUsage = null;
      // Retrieval happens here, before routing, so the router sizes and bills the prompt a model
      // will actually receive -- notes included.
      String text = resolve(retrieval, prompt);
      int tokens = tokenizer.encode(text).length;
      allTokens += tokens;
      // A session makes the router sticky: it adds a switch margin so a conversation does not
      // hop between models on a tie. Liveness checks are not conversation turns, so they carry
      // no session and cannot anchor the session to the smallest model.
      // Route on the instruction, size on the payload. The classifier answers by embedding its
      // input, and an embedding model has a context window like any other -- embeddinggemma's is
      // 2,048 tokens, so handing it a 147,019-token document throws rather than classifying.
      // Classifying the instruction is also what you want: "summarise this appendix" is the part
      // that says what kind of work this is, and the appendix itself says nothing about that.
      // estimatedTokens still carries the full size, because that is what the context-window
      // filter and the budget have to see.
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
                client -> client.respond(text),
                answer ->
                    lastRemoteUsage != null
                        ? lastRemoteUsage
                        : new RoutingUsage(tokens, estimateOutputTokens(answer)));
      } catch (RoutingBudgetExceededException denied) {
        // Reported, not fatal: one refused attempt should not discard the rest of the ledger.
        System.out.printf(
            "%-44s %-14s %-18s %d%n", abbreviate(prompt.text(), 42), "-", "refused", tokens);
        System.out.printf("    refused: %s%n", denied.getMessage());
        // New in Models 0.3.60: the spend is recoverable even though the guard refused the result.
        System.out.printf(
            "    billed anyway: %s input + %s completion, $%s%n",
            denied.billedUsage().map(u -> String.valueOf(u.inputTokens())).orElse("-"),
            denied.billedUsage().map(u -> String.valueOf(u.outputTokens())).orElse("-"),
            denied.billedCost().map(java.math.BigDecimal::toPlainString).orElse("-"));
        continue;
      }
      var chosen = result.decision().selected();
      if (chosen.local()) {
        localCompletionTokens += tokenizer.encode(String.valueOf(result.value())).length;
      } else {
        // The provider's own count supersedes the local tokenizer for the arm it bills, and the
        // local count is kept beside it so the share stays measured on one ruler.
        localRulerRemote += tokens;
        long in = lastRemoteUsage != null ? lastRemoteUsage.inputTokens() : tokens;
        long out = lastRemoteUsage != null ? lastRemoteUsage.outputTokens() : 0;
        remoteTokens += in;
        remoteCompletionTokens += out;
        remoteSpend.merge(chosen.id(), chosen.costOf(in, out), BigDecimal::add);
        remoteTokensBy.computeIfAbsent(chosen.id(), key -> new long[2]);
        remoteTokensBy.get(chosen.id())[0] += in;
        remoteTokensBy.get(chosen.id())[1] += out;
        escalated++;
      }
      long millis =
          result.attempts().isEmpty()
              ? 0
              : result.attempts().getLast().duration().toMillis();
      callMillis.computeIfAbsent(chosen.id(), key -> new ArrayList<>()).add(millis);
      System.out.printf(
          "%-32s %-20s %-32s %9d %7d%n",
          abbreviate(prompt.text(), 30),
          describeClassification(pretrained, text, result.decision().taskType()),
          abbreviate(chosen.id(), 32),
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
    System.out.printf("%-32s %5s %9s %9s %9s%n", "MODEL", "CALLS", "TOTAL MS", "MEAN MS", "SHARE");
    for (var entry : callMillis.entrySet()) {
      long total = entry.getValue().stream().mapToLong(Long::longValue).sum();
      System.out.printf(
          "%-32s %5d %9d %9d %8.1f%%%n",
          abbreviate(entry.getKey(), 32),
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
        "%d prompts, %d escalated to a remote provider, %d answered on local weights%n",
        work.size(), escalated, work.size() - escalated);

    // Two rulers, kept apart on purpose. The local tokenizer measures every prompt the same way,
    // which is what makes the share comparable; the provider's own count is what it bills.
    System.out.printf(
        "local ruler (qwen3-0.6b tokenizer): %d of %d input tokens were routed off this machine"
            + " (%.1f%%)%n",
        localRulerRemote, allTokens, 100.0 * localRulerRemote / allTokens);
    System.out.printf(
        "provider ruler (%s reported): %d input + %d completion tokens billed%n",
        PREMIUM, remoteTokens, remoteCompletionTokens);
    System.out.printf(
        "  the same prompt measured %d tokens locally, so the two rulers differ by %d%n",
        localRulerRemote, remoteTokens - localRulerRemote);
    System.out.printf("completions generated on local weights: %d tokens%n", localCompletionTokens);
    // ModelCandidate.costOf is new in Models 0.3.60 and is the arithmetic the shared budget
    // charges, so this ledger and the router's cannot drift. It belongs to the candidate that
    // actually ran: with one remote that was a detail, with three it is the whole point.
    // region: ledger
    if (!remoteSpend.isEmpty()) {
      System.out.printf("%-20s %8s %8s %12s%n", "REMOTE PROVIDER", "IN", "OUT", "COST");
      var total = BigDecimal.ZERO;
      for (var entry : remoteSpend.entrySet()) {
        long[] t = remoteTokensBy.get(entry.getKey());
        total = total.add(entry.getValue());
        System.out.printf(
            "%-20s %8d %8d %12s%n",
            entry.getKey(),
            t[0],
            t[1],
            "$" + entry.getValue().setScale(6, RoundingMode.HALF_UP).toPlainString());
      }
      System.out.printf(
          "%-20s %8d %8d %12s%n",
          "total",
          remoteTokens,
          remoteCompletionTokens,
          "$" + total.setScale(6, RoundingMode.HALF_UP).toPlainString());
    }
    // endregion
    var premiumCandidate =
        fleet.router().candidates().stream()
            .filter(candidate -> candidate.id().equals(PREMIUM))
            .findFirst()
            .orElseThrow();
    System.out.printf(
        "had every prompt gone to %s: $%s of input alone, plus $%s for the completions this"
            + " machine produced for nothing%n",
        PREMIUM,
        premiumCandidate.costOf(allTokens, 0).setScale(6, RoundingMode.HALF_UP).toPlainString(),
        premiumCandidate
            .costOf(0, localCompletionTokens)
            .setScale(6, RoundingMode.HALF_UP)
            .toPlainString());
    System.out.printf(
        "router-accounted spend: $%s of the $0.50 shared budget%n",
        budget.snapshot().spent().setScale(6, RoundingMode.HALF_UP).toPlainString());

    for (var open : OPEN.values()) {
      if (open instanceof AutoCloseable closeable) closeable.close();
    }
    retrieval.close();
    index.close();
  }

  /**
   * Four local models discovered from the catalog, three remote providers declared.
   *
   * <p>Only a remote candidate claims {@code reasoning}; only the grounder claims {@code
   * grounding}; only Harriet claims {@code decision}. The capability filter therefore settles
   * eligibility before any score is compared.
   */
  static ModelFleet<Responder> buildFleet(TaskClassifier classifier, VectorCollection retrieval) {
    // region: locals
    // Identity, locality, the context window read from the artifact and this host's throughput all
    // come from the catalog, so none of them is written here.
    var catalog = new LinkedHashMap<String, ModelCandidate>();
    for (var found : CatalogDiscovery.discover()) {
      catalog.put(found.id(), found);
    }

    // Only what a catalog cannot know: `liveness` and `grounding` are names this application
    // invented, and the quality weights are its judgement. `toBuilder` keeps the rest.
    //
    // Tags are a second filter, separate from capabilities and active only when non-empty: a model
    // tagged `chat` is refused outright for a prompt classified `summarization`. The catalog tags
    // these `chat` to describe the weights; this fleet selects on capability and quality, so the
    // tags are cleared.
    var tiny =
        discovered(catalog, TINY_ID)
            .tags(Set.of())
            .addCapabilities("liveness")
            .quality(Map.of("chat", 0.45))
            .build();
    var small =
        discovered(catalog, SMALL_ID)
            .tags(Set.of())
            .addCapabilities("summarization")
            .quality(Map.of("chat", 0.60, "summarization", 0.62))
            .build();
    var grounder =
        discovered(catalog, GROUNDER_ID)
            .tags(Set.of())
            .addCapabilities("grounding")
            .quality(Map.of("chat", 0.66, "grounding", 0.70))
            .build();
    // Harriet is the exception. The catalog reports the composite's base weights as a chat model,
    // true of the weights and wrong about this arm: three typed questions, three forward passes, no
    // generated prose. So `capabilities` replaces rather than adds -- a decision arm claiming `chat`
    // would be eligible for a customer's real question -- and tokens-per-second is overridden
    // because it does not describe this cost. The window carries through.
    var decisions =
        discovered(catalog, HARRIET_ID)
            .tags(Set.of())
            .capabilities(Set.of("decision"))
            .tokensPerSecond(1)
            .quality(Map.of("decision", 0.90))
            .build();
    // endregion
    // Three remote providers, not one. Each is an ordinary candidate with its own prices, ceiling
    // and client. Only the premium one claims `reasoning`. Their context windows -- 200k to 1M --
    // are what makes them the only candidates left for the appendix, and which of the three serves
    // it is then decided on policy rather than on vendor.
    // region: providers
    var premium =
        ModelCandidate.builder(PREMIUM)
            .local(false)
            .capabilities(Set.of("chat", "reasoning", "summarization"))
            .costPerMillionTokens(PREMIUM_IN, PREMIUM_OUT)
            // New in Models 0.3.60. A reasoning model bills its reasoning as completion, so it
            // cannot share an output ceiling with a model that answers a liveness check in eight
            // tokens. The execution-wide bound stays small for the local arms.
            .maxOutputTokens(PREMIUM_CAP)
            // New in Models 0.4.3, and the mirror of maxOutputTokens. The fleet-wide input bound
            // has to stay small, because the execution takes input + output as the context every
            // request must fit: raise it and a one-token liveness check demands a window no local
            // model has. So the ceiling belongs on the candidate that can honour it.
            // 272,000, not the 400,000 a tracker lists. The provider is the authority and it
            // says so in its own refusal: "Input tokens exceed the configured limit of 272000
            // tokens. Your messages resulted in 284034 tokens." A declared window that is too
            // generous does not fail at routing time; it fails at the provider, after the
            // request was built and sent.
            .maxInputTokens(272_000)
            .contextWindow(272000)
            .timeToFirstTokenMillis(850)
            .tokensPerSecond(90)
            .quality(Map.of("chat", 0.95, "reasoning", 0.96, "summarization", 0.94))
            .build();
    var economy =
        ModelCandidate.builder(ECONOMY)
            .local(false)
            .capabilities(Set.of("chat", "summarization"))
            .costPerMillionTokens(ECONOMY_IN, ECONOMY_OUT)
            .maxOutputTokens(ECONOMY_CAP)
            .maxInputTokens(1_000_000)
            .contextWindow(1000000)
            .timeToFirstTokenMillis(400)
            .tokensPerSecond(140)
            .quality(Map.of("chat", 0.82, "summarization", 0.86))
            .build();
    var haiku =
        ModelCandidate.builder(HAIKU)
            .local(false)
            .capabilities(Set.of("chat", "summarization"))
            .costPerMillionTokens(HAIKU_IN, HAIKU_OUT)
            // New in Models 0.4.0. The provider's step is "over 100k", and the threshold is
            // inclusive, so it is declared one token above. Crossing it reprices the whole
            // request, output included.
            .pricingTier(100_001, HAIKU_HIGH_IN, HAIKU_HIGH_OUT)
            .maxOutputTokens(HAIKU_CAP)
            .maxInputTokens(200_000)
            .contextWindow(200000)
            .timeToFirstTokenMillis(300)
            .tokensPerSecond(120)
            .quality(Map.of("chat", 0.80, "summarization", 0.83))
            .build();
    // endregion

    // region: wiring
    return ModelFleet.<Responder>builder()
        .classifier(classifier)
        // BALANCED weights quality 0.40 and latency 0.15, and picks qwen3-0.6b for a customer's
        // question. LOCAL_FIRST picks it too: every local arm scores identical locality, so a 0.35
        // thumb there separates nothing between them, and the LOCAL_ONLY boundary already keeps
        // these requests on this machine. FASTEST is the policy that changes the answer -- it
        // hands ordinary chat to the 360M model on latency alone, which is the wrong trade here.
        .policy(RoutingPolicy.BALANCED)
        .model(tiny, prompt -> acknowledge(TINY, prompt))
        .model(small, prompt -> chat(SMALL, prompt, 80))
        .model(grounder, fleet::ground)
        .model(decisions, fleet::decide)
        // One fleet, three remote clients. Each closure is where a provider's SDK would live, so
        // models-router never learns any of their names.
        .model(premium, prompt -> callOpenAi(PREMIUM, PREMIUM_CAP, prompt))
        .model(economy, prompt -> callOpenAi(ECONOMY, ECONOMY_CAP, prompt))
        .model(haiku, prompt -> callAnthropic(HAIKU, HAIKU_CAP, prompt))
        .build();
    // endregion
  }

  /**
   * The discovered candidate for one catalog id, as a builder ready to be adjusted.
   *
   * <p>Discovery reports only models whose weights are already on disk: `ModelJarsCatalog` checks
   * the descriptor's local path and then the content-addressed cache, and skips anything it does
   * not find. An absent id here therefore means the weights have not been fetched yet, which is
   * why the arms above are warmed first.
   */
  static ModelCandidate.Builder discovered(Map<String, ModelCandidate> catalog, String id) {
    var found = catalog.get(id);
    if (found == null) {
      throw new IllegalStateException(
          "no catalog entry for "
              + id
              + "; discovery found "
              + catalog.keySet()
              + ". Weights are fetched when a runtime is opened, so this means warming did not"
              + " run or did not complete.");
    }
    return found.toBuilder();
  }

  /**
   * A billing appendix long enough that no local arm in this fleet can hold it.
   *
   * <p>The local chat models' context windows are 8,192, 40,960 and 131,072 tokens, read from their
   * artifacts by the catalog. This is built to exceed all three, so the router's own
   * {@code contextWindow < estimatedTokens} filter -- not a capability label -- is what leaves only
   * the remote candidates eligible. Generated rather than stored so the repository does not carry
   * a megabyte of filler, and deterministic so every run measures the same input.
   *
   * <p>It is also sized well past Haiku's 200,000-token window rather than just past the local
   * ones, because eligibility is decided on a local estimate and billed on the provider's count,
   * and the two disagree by more than the margin would survive. Measured on this document at half
   * this length: 147,011 tokens by the local qwen3-0.6b tokenizer, 141,534 at OpenAI, and 219,559
   * at Anthropic. A 147k estimate fits a 200k window; the 219k the provider actually counted does
   * not, and the attempt was refused after it had been paid for.
   */
  static String appendix() {
    var text = new StringBuilder(1_500_000);
    text.append(
        "Appendix B. Billing reconciliation and refund policy, consolidated clauses.\n\n");
    for (int clause = 1; clause <= 2_500; clause++) {
      text.append("Clause ")
          .append(clause)
          .append(". Under settlement variant ")
          .append(clause % 37)
          .append(", a refund is issued to the original payment method within five business days,")
          .append(" unless the originating charge was already reconciled in the same nightly")
          .append(" cycle, in which case the automatic reversal takes precedence and the refund")
          .append(" is voided to avoid crediting the cardholder twice. Reconciliation runs at")
          .append(" 02:00 UTC and retries twice on failure; a reversal that fails twice is")
          .append(" escalated to the billing queue with the original charge id.\n");
    }
    return text.toString();
  }

  /**
   * One turn of the conversation.
   *
   * @param text what the user typed
   * @param requirements what answering it needs
   * @param session conversation id, or null for a turn that carries no history
   * @param retrieve whether this turn is grounded, and so must have context retrieved and attached
   *     before any model sees it
   */
  record Prompt(
      String text,
      RoutingRequirements requirements,
      String session,
      boolean retrieve,
      String attachment) {

    Prompt(String text, RoutingRequirements requirements, String session) {
      this(text, requirements, session, false, null);
    }

    Prompt(String text, RoutingRequirements requirements, String session, boolean retrieve) {
      this(text, requirements, session, retrieve, null);
    }
  }

  /**
   * The text a model actually receives, retrieval included.
   *
   * <p>Both arms call this, so a grounded question is byte-identical whether it is answered locally
   * or by a provider. Retrieval happens per call, as it would in a real system: embed the question,
   * search the collection, attach what comes back. Skipping it in one arm would make that arm look
   * cheaper for a reason that has nothing to do with routing -- it would simply be answering a
   * different, shorter question.
   */
  static String resolve(VectorCollection retrieval, Prompt prompt) {
    if (prompt.attachment() != null) {
      return prompt.text() + "\n\n" + prompt.attachment();
    }
    if (!prompt.retrieve()) {
      return prompt.text();
    }
    var embedding = (EmbeddingBackend) OPEN.get(EMBEDDER);
    var hits =
        retrieval.search(SearchRequest.builder(embedding.embed(prompt.text()), 2).build()).hits();
    var context = new StringBuilder();
    for (var hit : hits) {
      context.append(hit.document().text()).append(' ');
    }
    return "Notes: "
        + context.toString().strip()
        + "\nUsing only those notes, answer in one sentence. If they do not contain the answer,"
        + " say that you do not know.\nQuestion: "
        + prompt.text();
  }

  /** One support session: liveness, follow-ups, closed decisions, grounded questions, synthesis. */
  static List<Prompt> prompts() {
    // region: requirements
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
    // Nothing here says "go remote". The appendix is larger than any local arm's context window,
    // so ModelRouter.eligible rules them out on `contextWindow < estimatedTokens` and only the
    // three remotes are left. Which of them serves it is a policy question, not a vendor decision
    // written into the code.
    var longDocument = RoutingRequirements.builder().requireCapability("summarization").build();
    // endregion
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
        new Prompt("When is a refund issued, and to which payment method?", grounded, "s-1", true),
        new Prompt("What happens to a duplicate charge?", grounded, "s-1", true),
        new Prompt(
            "Our refund policy promises five business days to the original payment method, while"
                + " duplicate charges reverse automatically on the nightly reconciliation. Those"
                + " two paths can disagree for a customer who is both refunded and reconciled."
                + " Work out where they conflict and draft the terms-of-service paragraph that"
                + " resolves it.",
            synthesis,
            "s-1"),
        new Prompt(
            "Summarise this appendix for the support handbook, in two sentences.",
            longDocument,
            null,
            false,
            appendix()));
  }

  /** Sends every prompt to the provider and totals its own reported usage. */
  /**
   * The same conversation with no router: every prompt to one frontier model.
   *
   * <p>This is the baseline the routed arm is measured against, and it is deliberately the obvious
   * implementation -- one client, one model, one loop.
   */
  static void allRemote(VectorCollection retrieval) throws Exception {
    long input = 0;
    long output = 0;
    long sessionStart = System.nanoTime();
    long accounted = 0;
    // region: baseline
    System.out.printf("%n%-46s %8s %8s %8s%n", "PROMPT", "IN", "OUT", "MS");
    for (var prompt : prompts()) {
      lastRemoteUsage = null;
      long began = System.nanoTime();
      var answer = callOpenAi(PREMIUM, PREMIUM_CAP, resolve(retrieval, prompt));
      long millis = (System.nanoTime() - began) / 1_000_000;
      accounted += millis;
      if (lastRemoteUsage == null) {
        System.out.printf("%-46s   no usage reported: %s%n", abbreviate(prompt.text(), 44), answer);
        continue;
      }
      input += lastRemoteUsage.inputTokens();
      output += lastRemoteUsage.outputTokens();
      System.out.printf(
          "%-46s %8d %8d %8d%n",
          abbreviate(prompt.text(), 44),
          lastRemoteUsage.inputTokens(),
          lastRemoteUsage.outputTokens(),
          millis);
    }
    // endregion
    long sessionMillis = (System.nanoTime() - sessionStart) / 1_000_000;
    // Priced by the same ModelCandidate.costOf the routed ledger uses, rather than by a second
    // copy of the formula that could drift from it.
    var premium =
        ModelCandidate.builder(PREMIUM)
            .local(false)
            .costPerMillionTokens(PREMIUM_IN, PREMIUM_OUT)
            .build();
    System.out.printf("%n== every prompt through %s ==%n", PREMIUM);
    System.out.printf("provider-reported: %d input + %d completion tokens%n", input, output);
    System.out.printf(
        "at the declared $%.2f/M in, $%.2f/M out: $%s%n",
        PREMIUM_IN,
        PREMIUM_OUT,
        premium.costOf(input, output).setScale(6, RoundingMode.HALF_UP).toPlainString());
    System.out.printf(
        "conversation wall clock: %d ms, of which %d ms (%.1f%%) was model calls%n",
        sessionMillis, accounted, 100.0 * accounted / sessionMillis);
    System.out.println("No local weights are loaded, so there is no startup cost to amortise.");
    System.out.println(
        "Retrieval ran for the grounded prompts here exactly as it does in the routed arm, so both");
    System.out.println("arms sent byte-identical text and the comparison is like for like.");
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
  /** The grounded arm receives an already-retrieved prompt, so it only generates. */
  static String ground(String groundedPrompt) {
    return generate(GROUNDER, groundedPrompt, 64);
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

  /**
   * One provider's client. Two candidates bind to this with different models, prices and ceilings,
   * which is all "a second provider" means to the fleet.
   */
  static String callOpenAi(String model, int cap, String prompt) throws Exception {
    var key = System.getenv("OPENAI_API_KEY");
    if (key == null || key.isBlank()) {
      return "[routed to " + model + "; not executed because OPENAI_API_KEY is unset]";
    }
    var mapper = new ObjectMapper();
    var message = mapper.createObjectNode().put("role", "user").put("content", prompt);
    var body =
        mapper
            .createObjectNode()
            .put("model", model)
            .put("max_completion_tokens", cap)
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
              model,
              response.statusCode(),
              parsed.path("error").path("message").asText(response.body()));
    }
    var usage = parsed.path("usage");
    if (usage.hasNonNull("prompt_tokens")) {
      lastRemoteUsage =
          new RoutingUsage(
              usage.path("prompt_tokens").asLong(), usage.path("completion_tokens").asLong());
    }
    return parsed.path("choices").path(0).path("message").path("content").asText("");
  }

  /**
   * A different vendor's client: different endpoint, credential, auth header and response shape.
   * The fleet does not know any of that; it holds a candidate and something callable.
   */
    // region: anthropic
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
    // endregion

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

  /**
   * What the classifier saw, not merely what it returned.
   *
   * <p>`match` is new in Models 0.3.60. `classify` answers with a task or with nothing, so a
   * conversational prompt unlike every work-shaped exemplar and one that nearly matched both print
   * as the same dash. The nearest task and its similarity say which happened.
   */
  static String describeClassification(
      PretrainedTaskClassifier classifier, String prompt, String classified) {
    if (classified != null) return classified;
    return classifier
        .match(prompt)
        .map(match -> "~%s %.2f".formatted(match.task(), match.similarity()))
        .orElse("-");
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
