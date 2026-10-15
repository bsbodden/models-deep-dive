//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.58
//DEPS org.modeljars.huggingface:ggml-org.embeddinggemma-2-gguf.q8_0:2.0.0-q8_0.1

import java.util.Arrays;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class gemma {
  private static final String MODEL = "org.modeljars.huggingface:ggml-org.embeddinggemma-2-gguf.q8_0:2.0.0-q8_0.1";

  public static void main(String... args) {
    quietLibraries();
    var input = args.length == 0 ? "How can public transit connect neighborhoods?" : String.join(" ", args);
    long loadStarted = System.nanoTime();
    try (var model = ModelJars.openEmbedding(MODEL)) {
      long loaded = System.nanoTime();
      String query = "task: search result | query: " + input;
      var vector = model.embed(query);
      long completed = System.nanoTime();

      System.out.println("Query:     " + query);
      System.out.println("Document recipe: title: none | text: <document text>");
      System.out.printf("First eight components: %s%n", Arrays.toString(Arrays.copyOf(vector, Math.min(8, vector.length))));
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
