//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.61
//DEPS org.modeljars.huggingface:cactus-compute.needle2-cact.cq2_mixed:2.0.0-cq2_mixed.2
//DEPS com.fasterxml.jackson.core:jackson-databind:2.22.3

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.api.ToolCall;
import com.integrallis.models.api.ToolSpec;
import com.integrallis.models.runtime.GenerationMetrics;
import com.integrallis.models.runtime.ToolCallTokenConstraints;
import com.integrallis.models.runtime.chat.ChatMessage;
import com.integrallis.models.runtime.chat.ToolCallScanner;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class tools {
  private static final String MODEL = "org.modeljars.huggingface:cactus-compute.needle2-cact.cq2_mixed:2.0.0-cq2_mixed.2";
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final List<ToolSpec> TOOLS = List.of(
      new ToolSpec("set_lights", "Set a room's light brightness.",
          "{\"type\":\"object\",\"properties\":{\"room\":{\"type\":\"string\"},"
              + "\"brightness\":{\"type\":\"integer\",\"minimum\":0,\"maximum\":100}},"
              + "\"required\":[\"room\",\"brightness\"]}"),
      new ToolSpec("lock_door", "Lock a named exterior door.",
          "{\"type\":\"object\",\"properties\":{\"door\":{\"type\":\"string\"}},"
              + "\"required\":[\"door\"]}"));

  public static void main(String... args) throws Exception {
    quietLibraries();
    var request = args.length == 0 ? "Dim the bedroom lights to 20 percent and lock the front door." : String.join(" ", args);
    var home = new SmartHome();
    long loadStarted = System.nanoTime();
    try (var runtime = ModelJars.openRuntime(MODEL)) {
      long loaded = System.nanoTime();
      var prompt = runtime.chatTemplate().render(List.of(ChatMessage.user(request)), TOOLS);
      var constraint = ToolCallTokenConstraints.compile(
          runtime.tokenizer(), runtime.chatTemplate().toolSyntax(), TOOLS,
          ignored -> List.of()).orElseThrow();
      var options = SamplingOptions.builder().temperature(0).maxTokens(128).build();

      System.out.println("Request:      " + request);
      var output = runtime.pipeline().generate(prompt, options, constraint);
      System.out.println("Model output: " + output.strip());

      var calls = ToolCallScanner.scan(output, runtime.chatTemplate().toolSyntax()).toolCalls();
      System.out.println("Tool calls:   " + calls.size());
      for (var call : calls) {
        System.out.printf("  %s %s%n", call.name(), call.argumentsJson());
        home.execute(call);
      }
      home.printState();
      printMetrics(runtime.pipeline().lastGenerationMetrics(), loaded - loadStarted);
    }
  }

  private static void printMetrics(GenerationMetrics metrics, long loadNanos) {
    String ttft = metrics.timeToFirstToken()
        .map(value -> String.format("%,d ms", value.toMillis())).orElse("n/a");
    System.out.printf("%nMetrics:%n");
    System.out.printf("  Load                 %,d ms%n", loadNanos / 1_000_000);
    System.out.printf("  Tokenization         %,d ms%n", metrics.tokenization().toMillis());
    System.out.printf("  Prompt preparation   %,d ms%n", metrics.promptPreparation().toMillis());
    System.out.printf("  Prefill              %,d ms%n", metrics.prefill().toMillis());
    System.out.printf("  TTFT                 %s%n", ttft);
    System.out.printf("  Decode               %,d ms (%.1f tokens/s)%n",
        metrics.decode().toMillis(), metrics.decodeTokensPerSecond());
    System.out.printf("  Tokens               %,d prompt + %,d completion%n",
        metrics.usage().promptTokens(), metrics.usage().completionTokens());
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }

  private static final class SmartHome {
    private final Map<String, Integer> lights = new LinkedHashMap<>();
    private final Set<String> lockedDoors = new LinkedHashSet<>();

    void execute(ToolCall call) throws Exception {
      JsonNode arguments = JSON.readTree(call.argumentsJson());
      switch (call.name()) {
        case "set_lights" -> lights.put(
            requiredText(arguments, "room"), requiredInt(arguments, "brightness"));
        case "lock_door" -> lockedDoors.add(requiredText(arguments, "door"));
        default -> throw new IllegalArgumentException("Unknown tool: " + call.name());
      }
    }

    void printState() {
      System.out.println("Home state:");
      System.out.println("  Lights:       " + lights);
      System.out.println("  Locked doors: " + lockedDoors);
    }

    private static String requiredText(JsonNode arguments, String name) {
      JsonNode value = arguments.get(name);
      if (value == null || !value.isTextual() || value.textValue().isBlank()) {
        throw new IllegalArgumentException("Missing string argument: " + name);
      }
      return value.textValue();
    }

    private static int requiredInt(JsonNode arguments, String name) {
      JsonNode value = arguments.get(name);
      if (value == null || !value.isIntegralNumber() || !value.canConvertToInt()) {
        throw new IllegalArgumentException("Missing integer argument: " + name);
      }
      int brightness = value.intValue();
      if (brightness < 0 || brightness > 100) throw new IllegalArgumentException("Brightness must be 0..100");
      return brightness;
    }
  }
}
