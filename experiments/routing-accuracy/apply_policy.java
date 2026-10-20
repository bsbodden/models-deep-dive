//JAVA 25
//DEPS com.integrallis:models-rag:0.4.3
//DEPS com.fasterxml.jackson.core:jackson-databind:2.20.0

import com.fasterxml.jackson.databind.ObjectMapper;
import com.integrallis.models.rag.GroundedAnswerPolicy;
import com.integrallis.models.rag.GroundingDocument;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;

/**
 * Re-decides the local arm's collected answers through the library's grounding policy.
 *
 * The obvious objection to the routed arm's score on SQuAD v2 is that the fleet answered without
 * the policy the library ships for exactly this -- `GroundedAnswerPolicy`, which `rag.java` uses
 * and `fleet.java` does not. That objection is testable without spending anything: the policy is
 * deterministic post-processing of (question, evidence, generated text), and all three are already
 * in the committed result files. No model runs here and no prompt changes, so this arm is
 * comparable to the routed arm item for item.
 *
 * Each paragraph is handed over with a retrieval score of 1.0, above the policy's minimum, because
 * the dataset asserts these are the relevant paragraphs. That deliberately disables the
 * retrieval-score gate and leaves only what the policy decides from the answer itself, which is
 * the part under test.
 */
class apply_policy {

  static final ObjectMapper JSON = new ObjectMapper();

  public static void main(String... args) throws Exception {
    if (args.length < 1) {
      System.err.println("usage: apply_policy.java <dataset...>");
      System.exit(2);
    }
    var policy = new GroundedAnswerPolicy(0.25f);
    for (var dataset : args) {
      var sample = JSON.readTree(Files.readString(Path.of("sample-" + dataset + ".json")));
      var paragraphs = new LinkedHashMap<String, java.util.List<GroundingDocument>>();
      for (var item : sample) {
        var evidence = new ArrayList<GroundingDocument>();
        for (var paragraph : item.get("paragraphs")) {
          var id = "doc-" + (evidence.size() + 1);
          evidence.add(new GroundingDocument(id, id, paragraph.asText(), 1.0f, evidence.size() + 1));
        }
        paragraphs.put(item.get("id").asText(), evidence);
      }
      var questions = new LinkedHashMap<String, String>();
      for (var item : sample) {
        questions.put(item.get("id").asText(), item.get("question").asText());
      }

      var source = Path.of("results-qa-routed-" + dataset + ".jsonl");
      if (!Files.exists(source)) {
        System.out.printf("%s: no routed results to re-decide%n", dataset);
        continue;
      }
      var target = Path.of("results-qa-policy-" + dataset + ".jsonl");
      var decisions = new LinkedHashMap<String, Integer>();
      try (var writer = Files.newBufferedWriter(target)) {
        for (var line : Files.readAllLines(source)) {
          if (line.isBlank()) continue;
          var row = (com.fasterxml.jackson.databind.node.ObjectNode) JSON.readTree(line);
          var id = row.get("id").asText();
          var decided = policy.apply(questions.get(id), paragraphs.get(id), row.get("answer").asText());
          row.put("arm", "policy");
          row.put("rawAnswer", row.get("answer").asText());
          row.put("answer", decided.text());
          row.put("groundingDecision", decided.decision().name());
          decisions.merge(decided.decision().name(), 1, Integer::sum);
          writer.write(JSON.writeValueAsString(row));
          writer.newLine();
        }
      }
      System.out.printf("%s: %s%n", dataset, decisions);
    }
  }
}
