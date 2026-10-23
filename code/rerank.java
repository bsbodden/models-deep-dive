//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.65
//DEPS org.modeljars.huggingface:cstr.ms-marco-minilm-l-6-v2-gguf.q4_k_imatrix_g7c_f7:2.0.0-q4_k_imatrix_g7c_f7.2

import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class rerank {
  private static final String MODEL = "org.modeljars.huggingface:cstr.ms-marco-minilm-l-6-v2-gguf.q4_k_imatrix_g7c_f7:2.0.0-q4_k_imatrix_g7c_f7.2";

  public static void main(String... args) {
    quietLibraries();
    var query = args.length == 0 ? "How many people live in Berlin?" : String.join(" ", args);
    var documents = List.of(
        "Berlin has a population of 3,520,031 registered inhabitants.",
        "Paris is the capital and most populous city of France.",
        "Berlin is well known for its museums and metropolitan area.");
    long loadStarted = System.nanoTime();
    try (var model = ModelJars.openReranker(MODEL)) {
      long loaded = System.nanoTime();
      var ranked = model.rerank(query, documents);
      long completed = System.nanoTime();

      System.out.println("Query: " + query);
      System.out.println("Rank  Score       Document");
      for (int rank = 0; rank < ranked.size(); rank++) {
        var result = ranked.get(rank);
        System.out.printf("%4d  %10.6f  %s%n", rank + 1, result.score(), result.document());
      }
      System.out.printf("%nLoad:      %,d ms%n", (loaded - loadStarted) / 1_000_000);
      System.out.printf("Execution: %,d ms%n", (completed - loaded) / 1_000_000);
    }
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
