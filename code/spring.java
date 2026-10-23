//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.springframework.ai:spring-ai-bom:2.0.0@pom
//DEPS org.springframework.ai:spring-ai-client-chat
//DEPS com.integrallis:models-spring-ai:0.5.4
//DEPS org.modeljars:modeljars:0.1.65
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1

import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.spring.ai.ModelsSpringAiChatModel;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;
import org.springframework.ai.chat.client.ChatClient;

class spring {
  private static final String MODEL = "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";

  public static void main(String... args) {
    quietLibraries();
    var input = args.length == 0 ? "What is the capital of France? Reply with only the city name." : String.join(" ", args);
    var defaults = SamplingOptions.builder().temperature(0).maxTokens(64).build();
    long loadStarted = System.nanoTime();
    try (var runtime = ModelJars.openRuntime(MODEL)) {
      long loaded = System.nanoTime();
      var model = new ModelsSpringAiChatModel(
          runtime.model(),
          runtime.descriptor().alias(),
          runtime.chatTemplate(),
          defaults,
          runtime.descriptor().capabilities());

      System.out.println("Input:  " + input);
      var response = ChatClient.create(model).prompt().user(input).call().chatResponse();
      long completed = System.nanoTime();
      System.out.println("Output: " + response.getResult().getOutput().getText().strip());
      var usage = response.getMetadata().getUsage();
      System.out.printf("%nLoad:      %,d ms%n", (loaded - loadStarted) / 1_000_000);
      System.out.printf("Execution: %,d ms%n", (completed - loaded) / 1_000_000);
      System.out.printf("Tokens:    %,d prompt + %,d completion%n",
          usage.getPromptTokens(), usage.getCompletionTokens());
    }
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
