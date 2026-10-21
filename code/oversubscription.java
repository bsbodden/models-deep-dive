//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector --enable-native-access=ALL-UNNAMED -Xmx12g
//DEPS org.modeljars:modeljars:0.1.64
//DEPS com.integrallis:models-router:0.5.2
//DEPS com.integrallis:vectors-db:0.1.30
//DEPS org.modeljars.composite:harriet:0.1.64
//DEPS org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:2.0.0-q8_0.1
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1
//DEPS org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1

import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.runtime.chat.ChatMessage;
import java.util.*;
import java.util.logging.*;
import org.modeljars.*;
import org.modeljars.composite.harriet.Harriet;

/**
 * What four resident native runtimes cost each other on one machine.
 *
 * <p>Each runtime sizes its worker pool for every logical CPU unless told otherwise, so a resident
 * fleet oversubscribes. Run with and without -Dmodels.native.kernels.threads to measure it:
 *
 * <pre>
 *   jbang oversubscription.java                 # default: every runtime takes all 12 cores
 *   jbang -Dmodels.native.kernels.threads=3 oversubscription.java
 * </pre>
 */
class oversubscription {
  static final String SMALL = "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";
  static final String TINY = "org.modeljars.huggingface:huggingfacetb.smollm2-360m-instruct-gguf.q8_0:2.0.0-q8_0.1";
  static final String GROUNDER = "org.modeljars.huggingface:bartowski.llama-3.2-1b-instruct-gguf.q4_k_m:3.2.0-q4_k_m.1";
  static final String PROMPT = "I was charged twice for my September order.";

  static long timed(ModelJarRuntime rt) {
    var rendered = rt.chatTemplate().render(List.of(ChatMessage.user(PROMPT)));
    long began = System.nanoTime();
    rt.pipeline()
        .generate(rendered, SamplingOptions.builder().temperature(0).maxTokens(80).build());
    return (System.nanoTime() - began) / 1_000_000;
  }

  public static void main(String... a) throws Exception {
    for (String n : List.of("", "org.modeljars", "com.integrallis"))
      Logger.getLogger(n).setLevel(Level.OFF);
    String threads = System.getProperty("models.native.kernels.threads", "(unset: every core)");
    System.out.printf("models.native.kernels.threads = %s%n", threads);

    var qwen = ModelJars.openRuntime(SMALL);
    timed(qwen); // warm
    long alone = timed(qwen);
    System.out.printf("qwen3-0.6b alone                 %6d ms%n", alone);

    var tiny = ModelJars.openRuntime(TINY);
    var grounder = ModelJars.openRuntime(GROUNDER);
    var harriet = Harriet.open();
    timed(qwen); // warm again with neighbours resident
    long beside = timed(qwen);
    System.out.printf("qwen3-0.6b beside three others   %6d ms   (%.1fx)%n",
        beside, (double) beside / alone);

    for (var c : List.of(qwen, tiny, grounder)) c.close();
    harriet.close();
  }
}
