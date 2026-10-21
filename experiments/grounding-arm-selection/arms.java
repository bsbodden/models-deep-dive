//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx12g
//DEPS org.modeljars:modeljars:0.1.63
//DEPS com.integrallis:models-router:0.5.1
//DEPS com.fasterxml.jackson.core:jackson-databind:2.22.3
//DEPS org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1
//DEPS org.modeljars.huggingface:qwen.qwen3-8b-gguf.q4_k_m:3.0.0-q4_k_m.3
//DEPS org.modeljars.huggingface:bartowski.meta-llama-3.1-8b-instruct-gguf.q4_k_m:3.1.0-q4_k_m.2

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.runtime.chat.ChatMessage;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJar;
import org.modeljars.ModelJars;

/**
 * Answers the same grounded questions with each candidate arm, on one host in one run.
 *
 * The prompt is the one `routing-accuracy/accuracy.java` built, character for character, and the
 * samples are that experiment's committed files. Nothing here scores anything: it writes one JSON
 * object per item and `score.py` from that directory decides, so the thing producing the answers
 * cannot know what would count as a win.
 *
 * Latency and peak heap are recorded per item beside the answer, because an 8B model that reaches
 * parity has still bought it with something, and the trade belongs in the same log as the quality.
 */
class arms {

  record Arm(String name, String coordinate) {}

  static final List<Arm> LOCAL =
      List.of(
          new Arm("llama1b",
              "org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1"),
          new Arm("qwen3-8b", "org.modeljars.huggingface:qwen.qwen3-8b-gguf.q4_k_m:3.0.0-q4_k_m.3"),
          new Arm("llama3.1-8b",
              "org.modeljars.huggingface:bartowski.meta-llama-3.1-8b-instruct-gguf.q4_k_m:3.1.0-q4_k_m.2"));

  static final ObjectMapper JSON = new ObjectMapper();
  static final int MAX_ANSWER_TOKENS = 64;

  public static void main(String... args) throws Exception {
    if (args.length < 3) {
      System.err.println("usage: arms.java <arm> <sample.json> <limit> [offset]");
      System.err.println("  arm: frontier, or one of " + LOCAL.stream().map(Arm::name).toList());
      System.err.println("  offset: skip this many items first, default 0");
      System.exit(2);
    }
    quietLibraries();
    var armName = args[0];
    var sample = Path.of(args[1]);
    int limit = Integer.parseInt(args[2]);
    // An item window, not just a count. A 100-item 8B pass takes longer than the workstation can
    // supervise one foreground run for, and the account this runs on is capped at eight dedicated
    // cores, so the only way to measure the full sample is to measure it in halves and merge them.
    // The window is in the output's name, and the scorer refuses halves that overlap in disagreement.
    int offset = args.length > 3 ? Integer.parseInt(args[3]) : 0;
    var items = JSON.readTree(Files.readString(sample));
    var dataset = sample.getFileName().toString().replace("sample-", "").replace(".json", "");

    var rows = new java.util.ArrayList<LinkedHashMap<String, Object>>();
    // Every row is printed as JSON as it is produced, not only written at the end. A supervised run
    // that is killed before its last item -- which happened on 2026-10-20 after 76 of 100 items --
    // leaves the whole measurement on the floor otherwise, because the host is torn down with it.
    // The log is the fallback artifact: `grep '^{' log.txt` is the file.
    System.out.printf("%-6s %9s %9s %10s  %s%n", "ITEM", "PROMPT", "MS", "HEAP MIB", "ANSWER");

    if ("frontier".equals(armName)) {
      int index = 0;
      for (var item : items) {
        if (index++ < offset) continue;
        if (index > offset + limit) break;
        var row = answerRemotely(item, index);
        rows.add(row);
        System.out.println(JSON.writeValueAsString(row));
      }
    } else {
      var arm =
          LOCAL.stream()
              .filter(candidate -> candidate.name().equals(armName))
              .findFirst()
              .orElseThrow(() -> new IllegalArgumentException("unknown arm: " + armName));
      try (var runtime = ModelJars.openRuntime(ModelJar.of(arm.coordinate()))) {
        // One warm generation that nothing reads, so no measured item pays for the weight load.
        runtime.pipeline().generate(
            runtime.chatTemplate().render(List.of(ChatMessage.user("ready?"))),
            SamplingOptions.builder().temperature(0).maxTokens(4).build());
        int index = 0;
        for (var item : items) {
          if (index++ < offset) continue;
          if (index > offset + limit) break;
          var row = answerLocally(runtime, item, index);
          rows.add(row);
          System.out.println(JSON.writeValueAsString(row));
        }
      }
    }

    var target =
        Path.of("results-" + armName + "-" + dataset + (offset == 0 ? "" : ".from" + offset)
            + ".jsonl");
    try (var writer = Files.newBufferedWriter(target)) {
      for (var row : rows) {
        writer.write(JSON.writeValueAsString(row));
        writer.newLine();
      }
    }
    System.out.printf("%nwrote %d rows to %s%n", rows.size(), target);
  }

  /** The prompt from routing-accuracy/accuracy.java, unchanged, so the arms stay comparable. */
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

  static LinkedHashMap<String, Object> answerLocally(
      org.modeljars.ModelJarRuntime runtime, JsonNode item, int index) throws Exception {
    var prompt = promptFor(item);
    var rendered = runtime.chatTemplate().render(List.of(ChatMessage.user(prompt)));
    long began = System.nanoTime();
    var answer =
        runtime
            .pipeline()
            .generate(
                rendered,
                SamplingOptions.builder().temperature(0).maxTokens(MAX_ANSWER_TOKENS).build());
    long millis = (System.nanoTime() - began) / 1_000_000;
    var row = row(item, prompt, answer.strip(), millis);
    row.put("local", true);
    System.out.printf("%-6d %9d %9d %10d  %s%n", index, prompt.length(), millis, heapMiB(),
        abbreviate(answer.strip().replace('\n', ' '), 56));
    return row;
  }

  static LinkedHashMap<String, Object> answerRemotely(JsonNode item, int index) throws Exception {
    var prompt = promptFor(item);
    var key = System.getenv("OPENAI_API_KEY");
    if (key == null || key.isBlank()) {
      throw new IllegalStateException("OPENAI_API_KEY is unset and the frontier arm needs it");
    }
    var message = JSON.createObjectNode().put("role", "user").put("content", prompt);
    var body =
        JSON.createObjectNode().put("model", "gpt-5.1").put("max_completion_tokens", MAX_ANSWER_TOKENS);
    body.set("messages", JSON.createArrayNode().add(message));
    var request =
        HttpRequest.newBuilder(URI.create("https://api.openai.com/v1/chat/completions"))
            .header("Authorization", "Bearer " + key)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofMinutes(2))
            .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
            .build();
    long began = System.nanoTime();
    var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
    long millis = (System.nanoTime() - began) / 1_000_000;
    var parsed = JSON.readTree(response.body());
    if (response.statusCode() != 200) {
      throw new IllegalStateException(
          "gpt-5.1 returned HTTP " + response.statusCode() + ": " + response.body());
    }
    var answer = parsed.path("choices").path(0).path("message").path("content").asText("").strip();
    var row = row(item, prompt, answer, millis);
    row.put("local", false);
    row.put("providerInputTokens", parsed.path("usage").path("prompt_tokens").asLong(0));
    row.put("providerOutputTokens", parsed.path("usage").path("completion_tokens").asLong(0));
    System.out.printf("%-6d %9d %9d %10s  %s%n", index, prompt.length(), millis, "-",
        abbreviate(answer.replace('\n', ' '), 56));
    return row;
  }

  static LinkedHashMap<String, Object> row(JsonNode item, String prompt, String answer, long millis)
      throws Exception {
    var row = new LinkedHashMap<String, Object>();
    row.put("id", item.get("id").asText());
    row.put("promptSha256", sha256(prompt));
    row.put("millis", millis);
    row.put("heapMiB", heapMiB());
    row.put("answer", answer);
    return row;
  }

  static long heapMiB() {
    var runtime = Runtime.getRuntime();
    return (runtime.totalMemory() - runtime.freeMemory()) / (1024 * 1024);
  }

  static String sha256(String text) throws Exception {
    var digest = java.security.MessageDigest.getInstance("SHA-256");
    var hex = new StringBuilder();
    for (var b : digest.digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8))) {
      hex.append(String.format("%02x", b));
    }
    return hex.toString();
  }

  static String abbreviate(String text, int width) {
    return text.length() <= width ? text : text.substring(0, width - 1) + "…";
  }

  static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
