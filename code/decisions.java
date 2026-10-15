//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars.composite:harriet:0.1.58

import com.integrallis.models.decisions.Verdict;
import java.util.List;
import java.util.Map;
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
      //
      // Each outcome carries a written rule. Harriet's own javadoc records what that is worth:
      // accuracy 0.8917 with a rubric against 0.7500 without, measured 2026-09-24 over 120
      // JevBench items on the same model and kernel. Without one, the boolean below comes back
      // as a 0.50 coin flip on evidence a human reads at a glance.
      report(
          "billing?",
          Harriet.noul(
              harriet,
              "This ticket is about billing.",
              "the customer describes a charge, refund, invoice or subscription payment",
              "the customer describes delivery, product faults, accounts or anything not monetary",
              evidence));
      report(
          "queue",
          Harriet.choice(
              harriet,
              "Which queue should handle this?",
              List.of("billing", "technical", "shipping"),
              Map.of(
                  "billing", "charges, refunds, invoices and subscription payments",
                  "technical", "errors, outages and product faults",
                  "shipping", "delivery, tracking and returns in transit"),
              evidence));
      report(
          "urgency",
          Harriet.score(
              harriet,
              "How urgent is this ticket?",
              List.of("can wait", "this week", "today"),
              Map.of(
                  "can wait", "no money is at stake and nothing is blocked",
                  "this week", "money is at stake but the customer is not blocked",
                  "today", "the customer is out of pocket with no path forward"),
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
