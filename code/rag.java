//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars:modeljars:0.1.58
//DEPS com.integrallis:vectors-db:0.1.30
//DEPS com.integrallis:models-rag:0.3.59
//DEPS org.modeljars.huggingface:second-state.all-minilm-l6-v2-embedding-gguf.q4_k_m:2.0.0-q4_k_m.2
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1

import com.integrallis.models.api.SamplingOptions;
import com.integrallis.models.rag.*;
import com.integrallis.models.runtime.chat.ChatMessage;
import com.integrallis.vectors.core.Document;
import com.integrallis.vectors.core.SimilarityFunction;
import com.integrallis.vectors.db.*;
import java.util.*;
import org.modeljars.ModelJars;

class rag {
  static final String EMBEDDING = "org.modeljars.huggingface:second-state.all-minilm-l6-v2-embedding-gguf.q4_k_m:2.0.0-q4_k_m.2";
  static final String CHAT = "org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1";

  public static void main(String... args) {
    // Handwritten example data demonstrates wiring; it is not an evaluation corpus.
    var texts = List.of(
        "The museum opens at nine in the morning and closes at five in the afternoon.",
        "The library lends books for twenty-one days.",
        "The station ticket office accepts card payments.");
    var question = args.length == 0 ? "When does the museum open?" : String.join(" ", args);
    try (var embedding = ModelJars.openEmbedding(EMBEDDING)) {
      var query = embedding.embed(question);
      try (var collection = VectorCollection.builder().dimension(query.length)
          .metric(SimilarityFunction.COSINE).indexType(IndexType.FLAT).build()) {
        for (int i = 0; i < texts.size(); i++) {
          collection.add(new Document("doc-" + i, embedding.embed(texts.get(i)), texts.get(i), Map.of()));
        }
        collection.commit();
        var hits = collection.search(SearchRequest.builder(query, 2).build()).hits();
        var evidence = new ArrayList<GroundingDocument>();
        for (var hit : hits) {
          System.out.printf("Retrieved %s, score %.4f: %s%n", hit.id(), hit.score(), hit.document().text());
          evidence.add(new GroundingDocument(hit.id(), hit.id(), hit.document().text(), hit.score(), evidence.size() + 1));
        }
        // Demonstration threshold only. Calibrate on held-out data for a real application.
        var policy = new GroundedAnswerPolicy(0.25f);
        var prompt = GroundedRagPrompt.prepare(policy, question, evidence);
        if (!prompt.generationAllowed()) {
          System.out.println("RETRIEVAL_ABSTENTION: " + GroundedAnswerPolicy.ABSTENTION);
          return;
        }
        try (var runtime = ModelJars.openRuntime(CHAT)) {
          var rendered = runtime.chatTemplate().render(List.of(ChatMessage.user(prompt.text())));
          var raw = runtime.pipeline().generate(rendered,
              SamplingOptions.builder().temperature(0).maxTokens(96).build());
          var answer = policy.apply(question, evidence, raw);
          System.out.println("Raw model answer: " + raw.strip());
          System.out.println("Grounding outcome: " + answer.decision());
          System.out.println("Returned answer: " + answer.text());
        }
      }
    }
  }
}
