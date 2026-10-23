//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector
//RUNTIME_OPTIONS --enable-native-access=ALL-UNNAMED -Xmx6g
//DEPS org.modeljars:modeljars:0.1.65
//DEPS com.integrallis:models-router:0.5.4
//DEPS org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:3.0.0-q8_0.1
//DEPS org.modeljars.huggingface:ggml-org.qwen3-0.6b-gguf.q4_0:3.0.0-q4_0.1
//DEPS org.modeljars.huggingface:qwen.qwen3-8b-gguf.q4_k_m:3.0.0-q4_k_m.3

import com.integrallis.models.api.catalog.ModelCatalogProvider;
import com.integrallis.models.router.CatalogDiscovery;
import com.integrallis.models.router.TaskClassifier;
import com.integrallis.models.router.TaskIndexResource;
import org.modeljars.ModelJars;
import com.integrallis.models.router.ModelCandidate;
import com.integrallis.models.router.ModelFleet;
import com.integrallis.models.router.PretrainedTaskClassifier;
import com.integrallis.models.router.RoutingDataBoundary;
import com.integrallis.models.router.RoutingPolicy;
import com.integrallis.models.router.RoutingRequest;
import com.integrallis.models.router.RoutingRequirements;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.Logger;

/**
 * What happens to a fleet when a better model for one kind of work arrives.
 *
 * <p>This script does not add a model, change a requirement, or declare a quality. It routes one
 * tool-use prompt and prints which candidate won and why. Run it twice -- once before a
 * tool-qualified model's weights are on this machine and once after -- and the routing changes,
 * because {@code ModelJarsCatalog} reports <em>only cached artifacts</em> and carries each one's
 * measured qualification with it.
 *
 * <p>So "adding a model" is two acts a user already performs: put the coordinate on the classpath,
 * and open it once so the weights land. Everything the router then knows about it -- that it can
 * take tool calls, and how well it was measured doing so -- comes from the catalog, not from this
 * file. The companion runner moves the artifact out of the cache and back to produce the two
 * states; nothing here hides a candidate.
 *
 * <p>Prints, per phase: every discovered candidate with its tags and whether it carries a
 * <em>measured</em> tool-use quality, then the winner and the score breakdown that chose it.
 */
public class arrival {

  /** One tool-use request. Deliberately the kind of prompt the classifier labels `tool-use`. */
  static final String PROMPT = "Call the get_order_status function with order id 88412.";

  /** The embedder the shipped task index was built with; classification stays on this machine. */
  static final String EMBEDDER =
      "org.modeljars.huggingface:ggml-org.embeddinggemma-300m-gguf.q8_0:3.0.0-q8_0.1";

  /** The task label the fleet routes on, and the one the catalog maps `tool-calling` onto. */
  static final String TASK = "tool-use";

  public static void main(String[] args) throws Exception {
    quiet();
    System.out.printf("== phase: %s%n", args.length > 0 ? args[0] : "unlabelled");

    // Every candidate this machine can actually run, straight from the installed catalogs. No
    // filtering: a candidate missing from this list is a candidate whose weights are not here.
    List<ModelCandidate> discovered = CatalogDiscovery.discover();
    System.out.printf("catalogs installed: %d%n", installedCatalogs());
    System.out.printf("candidates discovered: %d%n", discovered.size());

    System.out.printf(
        "%n%-46s %-22s %-9s %s%n", "CANDIDATE", "TAGS", "TOOL-USE", "CONTEXT");
    List<ModelCandidate> toolCapable = new ArrayList<>();
    for (ModelCandidate candidate : discovered.stream()
        .sorted(Comparator.comparing(ModelCandidate::id))
        .toList()) {
      OptionalDouble measured = candidate.measuredQualityFor(TASK);
      boolean tagged = candidate.tags().contains(TASK);
      if (tagged) {
        toolCapable.add(candidate);
      }
      // `measuredQualityFor` is an OptionalDouble on purpose: absent is not zero. A model nobody
      // measured on this task and a model measured at zero are different facts, and 0.5.x stopped
      // collapsing them.
      System.out.printf(
          "%-46s %-22s %-9s %d%n",
          candidate.id().length() > 45 ? candidate.id().substring(0, 45) : candidate.id(),
          String.join(",", candidate.tags()).isEmpty() ? "-" : String.join(",", candidate.tags()),
          measured.isPresent() ? String.format("%.3f", measured.getAsDouble()) : "unmeasured",
          candidate.contextWindow());
    }
    System.out.printf(
        "%ncandidates tagged %s: %d%n", TASK, toolCapable.size());
    for (ModelCandidate candidate : toolCapable) {
      OptionalDouble measured = candidate.measuredQualityFor(TASK);
      System.out.printf(
          "  %-44s %s%n",
          candidate.id(),
          measured.isPresent()
              ? String.format(
                  "carries a measured %s quality of %.3f, from the catalog's own tool"
                      + " qualification",
                  TASK, measured.getAsDouble())
              : "no measured " + TASK + " quality; scores the policy's neutral prior");
    }

    // The fleet. Nothing below mentions a model by name: every candidate discovery reported is
    // offered, and the requirement asks for the task and nothing else.
    var embedding = ModelJars.openEmbedding(EMBEDDER);
    var index = TaskIndexResource.openBundled();
    var pretrained = PretrainedTaskClassifier.using(index, embedding::embed, 0.60);
    var classifier = TaskClassifier.local(pretrained);
    var fleet = ModelFleet.<String>builder().classifier(classifier).policy(RoutingPolicy.BALANCED);
    for (ModelCandidate candidate : discovered) {
      // The client is a label, not a runtime: this run measures which candidate the router picks,
      // and loading every discovered model to answer one prompt would measure something else.
      fleet.model(candidate, candidate.id());
    }
    var built = fleet.build();

    // Nothing is required but staying local. No capability, no tag, no minimum quality: the only
    // thing that differs between the two phases of this demo is which candidates exist, so the
    // requirement must not be what selects them.
    var requirement =
        RoutingRequirements.builder().dataBoundary(RoutingDataBoundary.LOCAL_ONLY).build();

    System.out.printf("%n-- routing one %s prompt%n", TASK);
    System.out.printf("   prompt: %s%n", PROMPT);
    var match = pretrained.match(PROMPT);
    boolean admitted = match.isPresent() && pretrained.admits(match.get());
    System.out.printf(
        "   classified: %s%n",
        match.isPresent()
            ? String.format(
                "%s%s %.3f",
                admitted ? "" : "~",
                match.get().task(),
                match.get().similarity())
            : "no nearest task");
    System.out.printf(
        "   task label used for the quality term: %s%n",
        admitted ? match.get().task() : "none; every candidate scores the same quality");
    // Two policies over the same fleet and the same prompt. One number decides nothing on its
    // own: quality is one weighted term of five, so a model measured slightly lower can still be
    // the right choice, and a reader deserves to see which policy would disagree.
    for (var policy : List.of(Map.entry("BALANCED", RoutingPolicy.BALANCED),
                              Map.entry("BEST_QUALITY", RoutingPolicy.BEST_QUALITY))) {
      try {
        var decision =
            built
                .router()
                .route(
                    RoutingRequest.builder(PROMPT).build(),
                    policy.getValue(),
                    com.integrallis.models.router.RoutingContinuity.none(),
                    requirement);
        var winner = decision.selected();
        System.out.printf(
            "%n   [%s] SELECTED %s%n", policy.getKey(), winner.id());
        System.out.printf(
            "     measured %s quality: %s | context %d | local %s%n",
            TASK,
            winner.measuredQualityFor(TASK).isPresent()
                ? String.format("%.3f", winner.measuredQualityFor(TASK).getAsDouble())
                : "unmeasured",
            winner.contextWindow(),
            winner.local());
        System.out.printf("     score %.4f%n", decision.score());
        for (var term : new java.util.TreeMap<>(decision.scoreBreakdown()).entrySet()) {
          System.out.printf("       %-16s %.4f%n", term.getKey(), term.getValue());
        }
        System.out.printf(
            "     runners-up: %s%n",
            decision.fallbacks().stream().limit(3).map(ModelCandidate::id).toList());
      } catch (RuntimeException e) {
        // Nothing eligible is a legitimate outcome, not a defect: print the refusal and its reason.
        System.out.printf("%n   [%s] NO ELIGIBLE MODEL: %s%n", policy.getKey(), e.getMessage());
      }
    }
  }

  private static int installedCatalogs() {
    int count = 0;
    for (ModelCatalogProvider ignored : java.util.ServiceLoader.load(ModelCatalogProvider.class)) {
      count++;
    }
    return count;
  }

  private static void quiet() {
    LogManager.getLogManager().reset();
    Logger.getLogger("").setLevel(Level.OFF);
    Logger.getLogger("com.integrallis").setLevel(Level.OFF);
    Logger.getLogger("org.modeljars").setLevel(Level.OFF);
  }
}
