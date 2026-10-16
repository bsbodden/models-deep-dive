//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.60
//DEPS com.integrallis:models-router:0.4.0
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1
//DEPS org.modeljars.huggingface:qwen.qwen2.5-0.5b-instruct.bf16:2.5.0-bf16.2

import com.integrallis.models.router.*;
import org.modeljars.ModelJarsCatalog;

class route {
  public static void main(String... args) {
    // Run chat.java and safetensors.java first: discovery does not download weights.
    var discovered = new ModelJarsCatalog().discover();
    if (discovered.isEmpty()) throw new IllegalStateException("Run the two chat examples first.");
    for (var model : discovered) {
      System.out.printf("%s: %s; performance=%s%n", model.id(), model.capabilities(),
          model.performance() == null ? "no matching host measurement" : model.performance());
    }
    var router = ModelRouter.discoverLocal().policy(RoutingPolicy.LOCAL_FIRST).build();
    var decision = router.route(
        RoutingRequest.builder(args.length == 0 ? "Explain a train timetable." : String.join(" ", args)).build(),
        RoutingRequirements.builder().requireCapability("chat")
            .dataBoundary(RoutingDataBoundary.LOCAL_ONLY).build());
    System.out.println(decision.explain());
    System.out.println("Selection only; no generation or remote call took place.");
  }
}
