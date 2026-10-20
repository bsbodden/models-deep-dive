//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.63
//DEPS org.modeljars.huggingface:walkingcat.soprano-1.1-80m-gguf.bf16:1.1.0-bf16.1

import com.integrallis.models.api.WavEncoder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.ModelJars;

class speech {
  private static final String MODEL = "org.modeljars.huggingface:walkingcat.soprano-1.1-80m-gguf.bf16:1.1.0-bf16.1";

  public static void main(String... args) throws Exception {
    quietLibraries();
    var input = args.length == 0 ? "The JVM can speak for itself." : String.join(" ", args);
    var output = Path.of("../recordings/speech.wav");
    long loadStarted = System.nanoTime();
    try (var model = ModelJars.openSpeech(MODEL)) {
      long loaded = System.nanoTime();
      var audio = model.synthesize(input);
      long completed = System.nanoTime();
      Files.createDirectories(output.toAbsolutePath().getParent());
      Files.write(output, WavEncoder.pcm16(audio));

      double synthesisMillis = (completed - loaded) / 1_000_000.0;
      System.out.println("Input: " + input);
      System.out.println("Audio: " + output.toAbsolutePath());
      System.out.printf("Duration: %,.0f ms at %,d Hz, %d channel%n",
          audio.duration().toNanos() / 1_000_000.0,
          audio.sampleRate(), audio.channels());
      System.out.printf("Load: %,d ms%n", (loaded - loadStarted) / 1_000_000);
      System.out.printf("Synthesis: %,.0f ms%n", synthesisMillis);
      System.out.printf("RTF: %.3f%n",
          synthesisMillis / (audio.duration().toNanos() / 1_000_000.0));
    }
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
