//JAVA 25
//DEPS com.fasterxml.jackson.core:jackson-databind:2.20.0

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

/**
 * Measures, from this machine, what each hosted model's first token and decode rate cost.
 *
 * `ModelCandidate` requires a time-to-first-token and a tokens-per-second for every candidate, and
 * for a hosted model there is nowhere to read them: no provider publishes either, and a catalog
 * cannot measure somebody else's network. fleet.java used to declare six such numbers -- 850 ms and
 * 90 tok/s, 400 and 140, 300 and 120 -- and every one of them was a guess.
 *
 * So they are measured. Each model is streamed a short prompt several times; the first content
 * delta gives the time to first token, and the completion-token count from the provider's own usage
 * block divided by the time after that gives the decode rate. Both are properties of this machine's
 * route to that provider on the day, which is exactly what a router selecting from this machine
 * needs, and the figures carry their n and their spread so nobody mistakes one sample for a
 * constant.
 */
class provider_speed {

  record Model(String vendor, String id, String envKey) {}

  static final List<Model> MODELS =
      List.of(
          new Model("openai", "gpt-5.1", "OPENAI_API_KEY"),
          new Model("openai", "gpt-4.1-mini", "OPENAI_API_KEY"),
          new Model("anthropic", "claude-haiku-5-5", "ANTHROPIC_API_KEY"));

  static final String PROMPT =
      "Count from one to twenty in words, separated by commas, and write nothing else.";
  static final int SAMPLES = 5;
  static final int CAP = 120;
  static final ObjectMapper JSON = new ObjectMapper();

  public static void main(String... args) throws Exception {
    int samples = args.length > 0 ? Integer.parseInt(args[0]) : SAMPLES;
    System.out.printf("%-20s %7s %10s %12s %14s%n",
        "MODEL", "SAMPLE", "TTFT MS", "COMPLETION", "DECODE TOK/S");
    var byModel = new LinkedHashMap<String, List<double[]>>();
    for (var model : MODELS) {
      var key = System.getenv(model.envKey());
      if (key == null || key.isBlank()) {
        System.out.printf("%-20s %s is unset, skipped%n", model.id(), model.envKey());
        continue;
      }
      var rows = new ArrayList<double[]>();
      for (int sample = 1; sample <= samples; sample++) {
        var measured = stream(model, key);
        if (measured == null) {
          continue;
        }
        rows.add(measured);
        System.out.printf("%-20s %7d %10.0f %12.0f %14.1f%n",
            model.id(), sample, measured[0], measured[1], measured[2]);
      }
      if (!rows.isEmpty()) {
        byModel.put(model.id(), rows);
      }
    }

    System.out.printf("%n%-20s %3s %12s %12s %16s%n",
        "MODEL", "N", "TTFT MEDIAN", "TTFT RANGE", "DECODE MEDIAN");
    for (var entry : byModel.entrySet()) {
      var rows = entry.getValue();
      double[] ttft = rows.stream().mapToDouble(row -> row[0]).sorted().toArray();
      double[] decode = rows.stream().mapToDouble(row -> row[2]).sorted().toArray();
      System.out.printf("%-20s %3d %12.0f %5.0f-%-6.0f %16.1f%n",
          entry.getKey(), rows.size(), ttft[ttft.length / 2], ttft[0], ttft[ttft.length - 1],
          decode[decode.length / 2]);
    }
    System.out.println();
    System.out.println("Declare the medians. A median of five is not a constant: the range above is");
    System.out.println("what the same prompt did on one machine within a few minutes.");
  }

  /** {ttftMillis, completionTokens, decodeTokensPerSecond}, or null when the call failed. */
  static double[] stream(Model model, String key) throws Exception {
    var request = model.vendor().equals("openai") ? openAi(model, key) : anthropic(model, key);
    long began = System.nanoTime();
    long firstToken = 0;
    long completionTokens = 0;
    var response =
        HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofLines());
    if (response.statusCode() != 200) {
      System.out.printf("%-20s HTTP %d%n", model.id(), response.statusCode());
      return null;
    }
    for (var line : (Iterable<String>) response.body()::iterator) {
      if (!line.startsWith("data: ")) {
        continue;
      }
      var payload = line.substring(6).trim();
      if (payload.equals("[DONE]")) {
        break;
      }
      JsonNode event = JSON.readTree(payload);
      // The first event carrying actual text is the first token. Role-only and ping events arrive
      // before it and are not output, so timing from them would flatter every provider that sends
      // one.
      if (firstToken == 0 && hasText(event)) {
        firstToken = System.nanoTime();
      }
      long reported = usageTokens(event);
      if (reported > 0) {
        completionTokens = reported;
      }
    }
    long ended = System.nanoTime();
    if (firstToken == 0 || completionTokens <= 1) {
      System.out.printf("%-20s no usable stream (first token %b, tokens %d)%n",
          model.id(), firstToken != 0, completionTokens);
      return null;
    }
    double ttftMillis = (firstToken - began) / 1.0e6;
    double decodeSeconds = (ended - firstToken) / 1.0e9;
    // The first token is already out, so the rate is over the ones that followed it.
    double decodeRate = decodeSeconds > 0 ? (completionTokens - 1) / decodeSeconds : 0;
    return new double[] {ttftMillis, completionTokens, decodeRate};
  }

  static boolean hasText(JsonNode event) {
    return !event.path("choices").path(0).path("delta").path("content").asText("").isEmpty()
        || !event.path("delta").path("text").asText("").isEmpty();
  }

  static long usageTokens(JsonNode event) {
    long openAi = event.path("usage").path("completion_tokens").asLong(0);
    if (openAi > 0) {
      return openAi;
    }
    return event.path("usage").path("output_tokens").asLong(0);
  }

  static HttpRequest openAi(Model model, String key) {
    var message = JSON.createObjectNode().put("role", "user").put("content", PROMPT);
    var body =
        JSON.createObjectNode()
            .put("model", model.id())
            .put("max_completion_tokens", CAP)
            .put("stream", true);
    body.set("messages", JSON.createArrayNode().add(message));
    // Without this the stream carries no usage block and the decode rate would have to be
    // estimated from the number of events, which is not a token count.
    body.set("stream_options", JSON.createObjectNode().put("include_usage", true));
    return HttpRequest.newBuilder(URI.create("https://api.openai.com/v1/chat/completions"))
        .header("Authorization", "Bearer " + key)
        .header("Content-Type", "application/json")
        .timeout(Duration.ofMinutes(2))
        .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
        .build();
  }

  static HttpRequest anthropic(Model model, String key) {
    var message = JSON.createObjectNode().put("role", "user").put("content", PROMPT);
    var body =
        JSON.createObjectNode()
            .put("model", model.id())
            .put("max_tokens", CAP)
            .put("stream", true);
    body.set("messages", JSON.createArrayNode().add(message));
    return HttpRequest.newBuilder(URI.create("https://api.anthropic.com/v1/messages"))
        .header("x-api-key", key)
        .header("anthropic-version", "2023-06-01")
        .header("Content-Type", "application/json")
        .timeout(Duration.ofMinutes(2))
        .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
        .build();
  }
}
