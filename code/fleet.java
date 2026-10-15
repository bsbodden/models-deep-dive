//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx6g
// Four models stay resident, and each native runtime otherwise sizes its persistent worker pool
// for every logical CPU. Four pools of twelve on twelve cores is oversubscription, and it cost
// 20x: qwen3-0.6b answered the same prompt in 1,169 ms alone and 23,946 ms beside the others.
// Three threads each shares the twelve this host has.
//RUNTIME_OPTIONS -Dmodels.native.kernels.threads=3
//DEPS org.modeljars:modeljars:0.1.58
//DEPS com.integrallis:models-router:0.3.59
//DEPS com.integrallis:vectors-db:0.1.30
//DEPS com.fasterxml.jackson.core:jackson-databind:2.22.3
//DEPS org.modeljars.composite:harriet:0.1.58
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
  // Declared contract prices, not measurements. Set these to your own agreement.
  static final double REMOTE_INPUT_PER_M = 1.25;
  static final double REMOTE_OUTPUT_PER_M = 10.00;
  static final String REMOTE_MODEL = "gpt-5.1";
  static final int REMOTE_OUTPUT_CAP = 2048;

  static final String EMBEDDER =
      "org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:3.0.0-q8_0.1";
  static final String TINY =
      "org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:2.0.0-q8_0.1";
  static final String SMALL =
      "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";
  static final String GROUNDER =
      "org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1";

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
