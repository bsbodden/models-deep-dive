//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.58
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1

import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.runtime.GenerationMetrics;
import com.integrallis.models.runtime.chat.ChatMessage;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class chat {
  private static final String MODEL = "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";

  public static void main(String... args) {
    quietLibraries();
    var input = args.length == 0 ? "What is the capital of France? Reply with only the city name." : String.join(" ", args);
    long loadStarted = System.nanoTime();
    try (var runtime = ModelJars.openRuntime(MODEL)) {
      long loaded = System.nanoTime();
      var prompt = runtime.chatTemplate().render(List.of(ChatMessage.user(input)));
      var options = SamplingOptions.builder().temperature(0).maxTokens(64).build();

      System.out.println("Input:  " + input);
      var answer = runtime.pipeline().generate(prompt, options);
      System.out.println("Output: " + answer.strip());
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
}
