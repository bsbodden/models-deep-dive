#!/usr/bin/env bash
# Assert the grounding guard's behaviour, including the path the default threshold never reaches.
#
# Three bugs in the guard's first version got past a reading of the code and past a normal run:
#
#   The grounding decision was recorded in one branch of resolve() and cleared in none, so the two
#   prompts after a grounded one printed a policy verdict for a policy that never saw them. Four
#   lines where there should have been two, and both extra lines looked like evidence.
#
#   A retrieval-level refusal returned the abstention string as the prompt, which would have asked
#   a model to answer the text "INSUFFICIENT_CONTEXT\nQuestion: ..." and billed for the reply. A
#   refusal is a decision not to generate, not a different thing to generate.
#
#   Neither could be caught by running the demo, because this corpus's retrieval scores clear the
#   default threshold on every grounded prompt. So the threshold is settable and this check raises
#   it to force the refusal.
#
# The all-remote arm runs with no API key on purpose: callOpenAi then reports instead of calling,
# so the refusal path is exercised for free rather than for the price of a 236k-token prompt.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/code"
strip() { grep -viE "^WARNING|incubator|^\[jbang\]|^Oct |^INFO|^Note:"; }
failures=0

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    printf 'ok    %-58s %s\n' "$label" "$actual"
  else
    printf 'FAIL  %-58s expected %s, got %s\n' "$label" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

echo "== default threshold: the guard runs and reports once per grounded prompt =="
routed="$(jbang fleet.java 2>&1 | strip)"
table="$(sed -n '/^PROMPT /,/== timing/p' <<<"$routed")"
check "grounding verdicts printed" 2 "$(grep -c 'grounding policy:' <<<"$table")"
check "grounded prompts answered locally" 2 \
  "$(grep -c 'bartowski_llama_3_2_1b' <<<"$table")"
# The liveness arm must not be eligible for a customer's question: before the capability
# declarations were corrected, "I was charged twice" was answered "still here" by a 360M model.
check "liveness model answers only heartbeats" 3 "$(grep -c 'smollm2_360m' <<<"$table")"
check "no abstentions at the default threshold" 0 "$(grep -c 'abstained' <<<"$table")"

echo
echo "== forced refusal: retrieval too weak, so no model runs in either arm =="
forced="$(jbang -Dfleet.grounding.minimumRetrievalScore=0.99 fleet.java 2>&1 | strip)"
forced_table="$(sed -n '/^PROMPT /,/== timing/p' <<<"$forced")"
check "grounded prompts abstain" 2 "$(grep -c 'abstained' <<<"$forced_table")"
check "abstentions are retrieval-level" 2 \
  "$(grep -c 'grounding policy: RETRIEVAL_ABSTENTION' <<<"$forced_table")"
check "the grounding model is never called" 0 \
  "$(grep -c 'bartowski_llama_3_2_1b' <<<"$forced_table")"

remote="$(env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY \
  jbang -Dfleet.grounding.minimumRetrievalScore=0.99 fleet.java all-remote 2>&1 | strip)"
remote_table="$(sed -n '/^PROMPT /,/every prompt/p' <<<"$remote")"
check "all-remote arm skips the same two prompts" 2 \
  "$(grep -cE '^[^ ].*  +-  +-  +-$' <<<"$remote_table")"

echo
echo "== quality floor: nothing in this fleet has a measured quality, so nothing routes =="
# The uncomfortable half of the evidence, asserted rather than described. Every qualified RAG
# artifact in the catalog is GUARDED_RAG, which measures a pipeline and not the model, and the
# hosted models carry no qualification at all now that their invented scores are deleted. A floor
# therefore refuses all ten prompts and names what is missing. If a measurement ever lands, this
# check fails and the article's claim has to be rewritten -- which is the correct trigger.
floored="$(jbang fleet.java require-quality 0.5 2>&1 | strip)"
floored_table="$(sed -n '/^PROMPT /,/== timing/p' <<<"$floored")"
check "every prompt is refused under a floor" 10 "$(grep -c 'refused' <<<"$floored_table")"
check "the reason names the missing measurement" 10 \
  "$(grep -c 'measured quality' <<<"$floored_table")"
check "no model answers under a floor" 0 \
  "$(grep -cE 'smollm2_360m|qwen3_0_6b|bartowski_llama|unsloth_qwen3|gpt-|claude-' <<<"$floored_table")"
check "a refusal is not fatal: the run still reports" 1 \
  "$(grep -c '== timing, warm ==' <<<"$floored")"

echo
if [ "$failures" -eq 0 ]; then
  echo "grounding guard: all checks passed"
else
  echo "grounding guard: $failures check(s) failed"
fi
exit "$failures"
