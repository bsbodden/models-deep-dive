//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx8g
//SOURCES ../../code/fleet.java

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.integrallis.models.api.EmbeddingBackend;
import com.integrallis.models.decisions.Choice;
import com.integrallis.models.router.*;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.modeljars.ModelJarDecisionRuntime;
import org.modeljars.ModelJars;
import org.modeljars.composite.harriet.Harriet;

/**
 * Scores the two arms of the article's comparison against public gold answers.
 *
 * The article publishes what each arm charged and how long it took, and says "not measured" for
 * accuracy, because its harness never scores an answer. This one does, on data nobody here wrote.
 *
 * It compiles the article's own fleet.java rather than redefining the fleet: the candidates, the
 * policy and the requirement objects under test are the ones the article shows. The protocol,
 * decision rule and kill criteria were frozen in README.md before this file ran.
 *
 * Both arms are handed a byte-identical prompt, built once per item by promptFor. The only
 * difference is which model answers it. Every item's answer, latency, token counts and selected
 * model go out as one JSON object per line, and scoring happens in score.py afterwards -- so the
 * measured path stays Java and nothing in this file knows whether it is winning.
 */
class accuracy {

  static final ObjectMapper JSON = new ObjectMapper();

  public static void main(String... args) throws Exception {
    if (args.length < 3) {
      System.err.println("usage: accuracy.java <qa|decide> <routed|api> <sample.json> [limit]");
      System.exit(2);
    }
    var stage = args[0];
    var arm = args[1];
    var sample = Path.of(args[2]);
    int limit = args.length > 3 ? Integer.parseInt(args[3]) : Integer.MAX_VALUE;

    fleet.quietLibraries();
    var items = JSON.readTree(Files.readString(sample));
    var out = new ArrayList<Map<String, Object>>();

    if ("qa".equals(stage)) {
      runGroundedQa(arm, items, limit, out);
    } else if ("decide".equals(stage)) {
      runDecisions(arm, items, limit, out, sample);
    } else {
      System.err.println("unknown stage: " + stage);
      System.exit(2);
    }

    var target = sample.resolveSibling(
        "results-" + stage + "-" + arm + "-" + sample.getFileName().toString()
            .replace("sample-", "").replace(".json", "") + ".jsonl");
    try (var writer = Files.newBufferedWriter(target)) {
      for (var row : out) {
        writer.write(JSON.writeValueAsString(row));
        writer.newLine();
      }
    }
    System.out.printf("%nwrote %d rows to %s%n", out.size(), target.getFileName());
  }

  /**
   * The prompt both arms receive for a grounded question.
   *
   * Every paragraph the dataset supplies goes in, for both arms, so the local model never answers
   * from less evidence than the frontier model gets. The abstention sentence is here because half
   * the SQuAD v2 sample has no answer in its paragraph, and a model that always guesses should not
   * score the same as one that declines.
   */
  static String promptFor(JsonNode item) {
    var notes = new StringBuilder();
    for (var paragraph : item.get("paragraphs")) {
      notes.append(paragraph.asText()).append('\n');
    }
    return "Notes:\n" + notes.toString().strip()
        + "\n\nUsing only those notes, answer with the shortest exact phrase from the notes that"
        + " answers the question. Do not explain. If the notes do not contain the answer, reply"
        + " exactly: I don't know.\nQuestion: " + item.get("question").asText();
  }

  static void runGroundedQa(String arm, JsonNode items, int limit, List<Map<String, Object>> out)
      throws Exception {
    var embedding = ModelJars.openEmbedding(fleet.EMBEDDER);
    fleet.OPEN.put(fleet.EMBEDDER, embedding);
    var index = TaskIndexResource.openBundled();
    var classifier = TaskClassifier.local(
        PretrainedTaskClassifier.using(index, embedding::embed, 0.60));
    var retrieval = fleet.buildRetrieval((EmbeddingBackend) embedding);

    ModelFleet<fleet.Responder> built = null;
    RoutingExecutionOptions options = null;
    if ("routed".equals(arm)) {
      // All four local arms, not just the one that answers. buildFleet names every candidate, and
      // discovery reports only models whose weights are already on disk -- opening a runtime is
      // what fetches them -- so warming one arm and building the fleet fails on the other three.
      // The fleet's own guard says so rather than quietly building a smaller fleet, which is how
      // this harness found out.
      warmLocalArms();
      // The article's own policy, with no floor: this experiment measures what the fleet's
      // selected models answer, and a floor would change which models answer rather than how well
      // they do. BALANCED is what fleet.java routes with by default.
      built = fleet.buildFleet(classifier, retrieval, RoutingPolicy.BALANCED);
      options = RoutingExecutionOptions.builder()
          .sharedBudget(new RoutingBudget(new BigDecimal("15.00")))
          // The article's fleet-wide bounds, except for input: a HotpotQA item carries ten
          // paragraphs, so the floor on required context has to admit them or every candidate is
          // ruled out and the stage measures the bound rather than the model.
          .tokenBounds(new RoutingTokenBounds(8192, 64))
          .timeout(Duration.ofMinutes(5))
          .build();
    }

    var grounded = RoutingRequirements.builder()
        .requireCapability("grounding")
        .dataBoundary(RoutingDataBoundary.LOCAL_ONLY)
        .build();
    assertMatchesFleet(grounded, "grounding");

    var tokenizer = fleet.runtime(fleet.SMALL).pipeline().tokenizer();
    int index0 = 0;
    System.out.printf("%n%-6s %-34s %9s %8s  %s%n", "ITEM", "SELECTED", "LOCAL IN", "MS", "ANSWER");
    for (var item : items) {
      if (index0++ >= limit) break;
      var prompt = promptFor(item);
      int tokens = tokenizer.encode(prompt).length;
      var row = new LinkedHashMap<String, Object>();
      row.put("id", item.get("id").asText());
      row.put("arm", arm);
      row.put("promptSha256", sha256(prompt));
      row.put("promptTokensLocalRuler", tokens);

      long began = System.nanoTime();
      String answer;
      String selected;
      if ("routed".equals(arm)) {
        var request = RoutingRequest.builder(item.get("question").asText())
            .estimatedTokens(tokens).build();
        var result = built.execute(request, grounded, RoutingContinuity.none(), options,
            client -> client.respond(prompt),
            reply -> new RoutingUsage(tokens, tokenizer.encode(String.valueOf(reply)).length));
        answer = String.valueOf(result.value());
        selected = result.decision().selected().id();
        row.put("local", result.decision().selected().local());
      } else {
        answer = fleet.callOpenAi(fleet.PREMIUM, 64, prompt);
        selected = fleet.PREMIUM;
        row.put("local", false);
        if (fleet.lastRemoteUsage != null) {
          row.put("providerInputTokens", fleet.lastRemoteUsage.inputTokens());
          row.put("providerOutputTokens", fleet.lastRemoteUsage.outputTokens());
        }
      }
      long millis = (System.nanoTime() - began) / 1_000_000;
      row.put("selected", selected);
      row.put("millis", millis);
      row.put("answer", answer);
      out.add(row);
      System.out.printf("%-6d %-34s %9d %8d  %s%n", index0, abbreviate(selected, 34), tokens,
          millis, abbreviate(answer.replace('\n', ' '), 60));
    }
  }

  /**
   * Loads every local arm the fleet names, and reports what each cost.
   *
   * Warming is not politeness. A cold load of these weights is seconds that would be charged to
   * the first item as if it were answer latency, and the article's own harness warms for the same
   * reason.
   */
  static void warmLocalArms() throws Exception {
    var warmers = new LinkedHashMap<String, fleet.Responder>();
    warmers.put(fleet.TINY_ID, text -> fleet.acknowledge(fleet.TINY, text));
    warmers.put(fleet.SMALL_ID, text -> fleet.complete(fleet.SMALL, List.of(
        com.integrallis.models.runtime.chat.ChatMessage.user(text)), 8));
    warmers.put(fleet.GROUNDER_ID, text -> fleet.complete(fleet.GROUNDER, List.of(
        com.integrallis.models.runtime.chat.ChatMessage.user(text)), 8));
    warmers.put(fleet.HARRIET_ID, text -> fleet.decide(text));
    for (var warm : warmers.entrySet()) {
      long began = System.nanoTime();
      warm.getValue().respond("ready?");
      System.out.printf("warmed %-34s %7d ms%n", abbreviate(warm.getKey(), 34),
          (System.nanoTime() - began) / 1_000_000);
    }
  }

  /**
   * The prompt both arms receive for a closed decision.
   *
   * Harriet scores the letters of a closed answer space and never generates, so its "prompt" is a
   * question, a label list and a rubric per label. The provider arm is handed the same three
   * things as text and asked for one label, so the comparison is between two models reading the
   * same rules rather than between a careful prompt and a careless one.
   */
  static String decisionPrompt(String text, List<String> labels, Map<String, String> criteria) {
    var rules = new StringBuilder();
    for (var label : labels) {
      rules.append("- ").append(label).append(": ").append(criteria.get(label)).append('\n');
    }
    return "Request: " + text
        + "\n\nWhich label describes the request above? Answer with one label and nothing else."
        + "\nLabels and what each one means:\n" + rules.toString().strip();
  }

  static void runDecisions(String arm, JsonNode items, int limit, List<Map<String, Object>> out,
      Path sample) throws Exception {
    var rubricFile = sample.resolveSibling(
        "rubrics-" + sample.getFileName().toString().replace("sample-", ""));
    var rubricJson = JSON.readTree(Files.readString(rubricFile));
    var question = rubricJson.get("question").asText();
    var labels = new ArrayList<String>();
    var criteria = new LinkedHashMap<String, String>();
    rubricJson.get("labels").fields().forEachRemaining(entry -> {
      labels.add(entry.getKey());
      criteria.put(entry.getKey(), entry.getValue().asText());
    });

    ModelJarDecisionRuntime harriet = null;
    if ("routed".equals(arm)) {
      harriet = Harriet.open();
      long began = System.nanoTime();
      Harriet.choice(harriet, question, labels, criteria, "ready?");
      System.out.printf("warmed Harriet in %d ms%n", (System.nanoTime() - began) / 1_000_000);
    }

    int index0 = 0;
    System.out.printf("%n%-6s %-22s %-22s %8s%n", "ITEM", "GOLD", "ANSWER", "MS");
    for (var item : items) {
      if (index0++ >= limit) break;
      var text = item.get("text").asText();
      var prompt = decisionPrompt(text, labels, criteria);
      var row = new LinkedHashMap<String, Object>();
      row.put("id", item.get("id").asText());
      row.put("arm", arm);
      row.put("gold", item.get("label").asText());
      row.put("promptSha256", sha256(prompt));

      long began = System.nanoTime();
      String answer;
      if ("routed".equals(arm)) {
        var verdict = Harriet.choice(harriet, question, labels, criteria, text);
        answer = verdict.winner();
        row.put("probability", verdict.probabilityOf(verdict.winner()));
        row.put("confidence", verdict.confidence());
        row.put("selected", fleet.HARRIET_ID);
        row.put("local", true);
      } else {
        answer = fleet.callOpenAi(fleet.PREMIUM, 16, prompt).strip();
        row.put("selected", fleet.PREMIUM);
        row.put("local", false);
        if (fleet.lastRemoteUsage != null) {
          row.put("providerInputTokens", fleet.lastRemoteUsage.inputTokens());
          row.put("providerOutputTokens", fleet.lastRemoteUsage.outputTokens());
        }
      }
      row.put("millis", (System.nanoTime() - began) / 1_000_000);
      row.put("answer", answer);
      out.add(row);
      System.out.printf("%-6d %-22s %-22s %8s%n", index0, item.get("label").asText(),
          abbreviate(answer, 22), row.get("millis"));
    }
    if (harriet != null) harriet.close();
  }

  /**
   * Fails if this file's requirement object is not the article's.
   *
   * Duplicating two builder lines is harmless; duplicating them wrongly would measure a different
   * routing rule than the article publishes, and nothing in a passing run would say so.
   */
  static void assertMatchesFleet(RoutingRequirements mine, String capability) {
    for (var prompt : fleet.prompts()) {
      if (prompt.requirements().requiredCapabilities().contains(capability)) {
        if (!prompt.requirements().equals(mine)) {
          throw new IllegalStateException(
              "this harness's " + capability + " requirement differs from fleet.java's: "
                  + mine + " against " + prompt.requirements());
        }
        return;
      }
    }
    throw new IllegalStateException("fleet.java declares no " + capability + " requirement");
  }

  static String sha256(String text) throws Exception {
    var digest = java.security.MessageDigest.getInstance("SHA-256");
    var bytes = digest.digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    var hex = new StringBuilder();
    for (var b : bytes) hex.append(String.format("%02x", b));
    return hex.toString();
  }

  static String abbreviate(String text, int width) {
    return text.length() <= width ? text : text.substring(0, width - 1) + "…";
  }
}
