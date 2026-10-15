//JAVA 25+
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED
//DEPS org.modeljars:modeljars:0.1.57
//DEPS org.modeljars.huggingface:ggml-org.embeddinggemma-2-gguf.q8_0:2.0.0-q8_0.1

import java.util.Arrays;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class ModelJarsDemo {
  private static final String MODEL = "org.modeljars.huggingface:ggml-org.embeddinggemma-2-gguf.q8_0:2.0.0-q8_0.1";

  public static void main(String... args) {
    quietLibraries();
    var input = args.length == 0 ? "task: search result | query: How can public transit connect neighborhoods?" : String.join(" ", args);
    long loadStarted = System.nanoTime();
    try (var model = ModelJars.openEmbedding(MODEL)) {
      long loaded = System.nanoTime();
      var vector = model.embed(input);
      long completed = System.nanoTime();

      System.out.println("Input:     " + input);
      System.out.printf("Embedding: %s%n", Arrays.toString(vector));
      System.out.printf("Dimensions: %,d%n", vector.length);
      System.out.printf("Load:       %,d ms%n", (loaded - loadStarted) / 1_000_000);
      System.out.printf("Execution:   %,d ms%n", (completed - loaded) / 1_000_000);
    }
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
