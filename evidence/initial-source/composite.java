//JAVA 25
//RUNTIME_OPTIONS --add-modules=jdk.incubator.vector --enable-native-access=ALL-UNNAMED -Xmx4g
//DEPS org.modeljars.composite:granite-answerability:0.1.55

import java.util.List;
import org.modeljars.composite.granite.GraniteAnswerability;

class composite {
  public static void main(String... args) {
    var question = args.length == 0 ? "In which German state is Aachen?" : String.join(" ", args);
    var documents = List.of(
        "Aachen is a spa city in North Rhine-Westphalia, Germany, near the Belgian and Dutch borders.",
        "Aachen Cathedral was consecrated in 805 and became the first German UNESCO World Heritage site in 1978.");
    var request = GraniteAnswerability.Request.of(documents, question);
    System.out.println("Question: " + question);
    System.out.println("Documents: " + documents);
    try (var hybrid = GraniteAnswerability.open()) {
      var verdict = GraniteAnswerability.classify(
          hybrid, request, GraniteAnswerability.Prefix.SHARED);
      System.out.println("Answerability: " + verdict.answerability());
      System.out.println("Raw output: " + verdict.output());
      System.out.println("Physical prefix sharing: " + verdict.physicallySharesPrefix());
      System.out.println("Shared prefix tokens: " + verdict.sharedPrefixTokens());
    }
  }
}
