//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars.composite:harriet:0.1.55

import com.integrallis.models.decisions.Verdict;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.composite.harriet.Harriet;

class decisions {
  public static void main(String... args) {
    quietLibraries();
    var evidence = args.length == 0 ? "I was charged twice for my September subscription and no refund arrived." : String.join(" ", args);

    System.out.println("Evidence: " + evidence);
    System.out.println();
    try (var harriet = Harriet.open()) {
      // One closed answer space per question. Nothing is generated, so there is no JSON to
      // repair and no decoding loop to bound: each answer is one forward pass.
      report("billing?", Harriet.noul(harriet, "Is this ticket about billing?", evidence));
      report(
          "queue",
          Harriet.choice(
              harriet,
              "Which queue should handle this?",
              List.of("billing", "technical", "shipping"),
              evidence));
      report(
          "urgency",
          Harriet.score(
              harriet,
              "How urgent is this ticket?",
              List.of("can wait", "this week", "today"),
              evidence));
    }
  }

  private static void report(String label, Verdict verdict) {
    System.out.printf(
        "  %-10s %-12s p=%.3f  confidence=%.2f%n",
        label, verdict.winner(), verdict.probabilityOf(verdict.winner()),
        verdict.confidence());
  }

  private static void quietLibraries() {
    Logger.getLogger("org.modeljars").setLevel(Level.WARNING);
    Logger.getLogger("com.integrallis").setLevel(Level.WARNING);
  }
}
