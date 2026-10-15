//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.59
//DEPS org.modeljars.huggingface:liquidai.lfm2.5-embedding-350m-gguf.q4_0:2.5.0-q4_0.1

import java.util.Arrays;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class embed {
  private static final String MODEL = "org.modeljars.huggingface:liquidai.lfm2.5-embedding-350m-gguf.q4_0:2.5.0-q4_0.1";

  public static void main(String... args) {
    quietLibraries();
    var input = args.length == 0 ? "Public transit connects people and cities." : String.join(" ", args);
    long loadStarted = System.nanoTime();
    try (var model = ModelJars.openEmbedding(MODEL)) {
      long loaded = System.nanoTime();
      var vector = model.embed(input);
      long completed = System.nanoTime();

      System.out.println("Input:     " + input);
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
