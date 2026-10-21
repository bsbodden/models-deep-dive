//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars.composite:harriet:0.1.64

import com.integrallis.models.decisions.Verdict;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.modeljars.composite.harriet.Harriet;

class decisions {
  static final boolean RUBRICS =
      Boolean.parseBoolean(System.getProperty("decisions.rubrics", "true"));

  /** The rule for an outcome, or nothing at all when the comparison is what is being measured. */
  static String rule(String text) {
    return RUBRICS ? text : "";
  }

  public static void main(String... args) {
    quietLibraries();
    var evidence = args.length == 0 ? "I was charged twice for my September subscription and no refund arrived." : String.join(" ", args);

    System.out.println("Evidence: " + evidence);
    System.out.println("Rubrics: " + (RUBRICS ? "attached to every outcome" : "none"));
    System.out.println();
    try (var harriet = Harriet.open()) {
      if (!RUBRICS) {
        try {
          Harriet.noul(harriet, "This ticket is about billing.", "", "", evidence);
          System.out.println("  the library accepted a rubric-less answer space");
        } catch (IllegalArgumentException refused) {
          System.out.println("  the library refuses a rubric-less answer space:");
          System.out.println("  " + refused.getClass().getName() + ": " + refused.getMessage());
        }
        return;
      }
      // One closed answer space per question. Nothing is generated, so there is no JSON to
      // repair and no decoding loop to bound: each answer is one forward pass.
      //
      // Each outcome carries a written rule. Harriet's own javadoc records what that is worth:
      // accuracy 0.8917 with a rubric against 0.7500 without, measured 2026-09-24 over 120
      // JevBench items on the same model and kernel. Without one, the boolean below comes back
      // as a coin flip on evidence a human reads at a glance.
      //
      // `-Ddecisions.rubrics=false` drops every rule and keeps everything else. It exists because
      // the article quotes a no-rubric result -- `false p=0.503 confidence=0.00`, from an earlier
      // version of this script -- and the run that produced it was not kept. What the flag shows
      // on the current library is better than that number: `AnswerSpaces.requireCriteria` refuses
      // to construct the answer space at all. A decision without a rubric is not a bad decision
      // any more, it is a compile-time-shaped error at runtime, and the exception is the evidence.
      report(
          "billing?",
          Harriet.noul(
              harriet,
              "This ticket is about billing.",
              rule("the customer describes a charge, refund, invoice or subscription payment"),
              rule("the customer describes delivery, product faults, accounts or anything not monetary"),
              evidence));
      report(
          "queue",
          Harriet.choice(
              harriet,
              "Which queue should handle this?",
              List.of("billing", "technical", "shipping"),
              Map.of(
                  "billing", rule("charges, refunds, invoices and subscription payments"),
                  "technical", rule("errors, outages and product faults"),
                  "shipping", rule("delivery, tracking and returns in transit")),
              evidence));
      report(
          "urgency",
          Harriet.score(
              harriet,
              "How urgent is this ticket?",
              List.of("can wait", "this week", "today"),
              Map.of(
                  "can wait", rule("no money is at stake and nothing is blocked"),
                  "this week", rule("money is at stake but the customer is not blocked"),
                  "today", rule("the customer is out of pocket with no path forward")),
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
