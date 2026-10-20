//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS com.integrallis:models:0.5.1
//DEPS com.integrallis:backend-java:0.5.1

import com.integrallis.models.api.BackendConfiguration;
import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.backend.purejava.PureJavaBackend;
import com.integrallis.models.runtime.InferencePipeline;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

class bonsai {
  private static final String SHA256 = "53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3";

  public static void main(String... args) throws Exception {
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
    Path weights = args.length == 0
        ? Path.of(System.getProperty("user.home"), ".jvllm/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf")
        : Path.of(args[0]);
    if (Files.size(weights) != 5_946_648_928L) throw new IllegalArgumentException("Wrong artifact size");
    var digest = MessageDigest.getInstance("SHA-256");
    try (var input = new DigestInputStream(Files.newInputStream(weights), digest)) {
      input.transferTo(OutputStream.nullOutputStream());
    }
    if (!HexFormat.of().formatHex(digest.digest()).equals(SHA256)) {
      throw new IllegalArgumentException("Artifact checksum does not match the pinned candidate");
    }

    System.out.println("Bonsai 2: verified 5.95 GB PTQ1_0 text artifact");
    System.out.println("Runtime compatibility demonstration; production qualification is pending.");
    String prompt = "The quick brown fox";
    var configuration = new BackendConfiguration(
        Map.of(), Map.of(PureJavaBackend.MAX_CONTEXT_LENGTH_PROPERTY, "64"), List.of());
    try (var pipeline = new InferencePipeline(PureJavaBackend.load(weights, configuration))) {
      var options = SamplingOptions.builder().temperature(0).maxTokens(8).build();
      System.out.println("Completion: " + prompt + pipeline.generate(prompt, options));
    }
  }
}
