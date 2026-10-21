# Everything that can be checked without a GPU, a provider key, or four gigabytes of weights.
#
# `make check` is what CI runs. It is deliberately the same command a reader can run: a gate that
# only exists inside a workflow file is a gate nobody can reproduce.

PYTHON ?= python3

.PHONY: check scores figures gate article derived measured

check: scores figures gate gate-tests article derived

## Re-derive every experiment's RESULTS.json and MEASUREMENTS.json from the committed raw rows.
## Fails if a scored number in the repository cannot be reproduced from the artifacts beside it.
scores:
	$(PYTHON) experiments/routing-accuracy/score.py > /dev/null
	$(PYTHON) experiments/routing-accuracy/error_analysis.py > /dev/null
	$(PYTHON) experiments/grounding-arm-selection/score_arms.py > /dev/null
	$(PYTHON) experiments/grounding-arm-selection/score_arms.py \
	  experiments/grounding-arm-selection/screen > /dev/null
	$(PYTHON) experiments/local-only-chat/score_chat.py > /dev/null
	$(PYTHON) experiments/decision-threshold/tune.py all > /dev/null
	$(PYTHON) experiments/decision-threshold/score.py > /dev/null
	$(PYTHON) experiments/decision-threshold/check_findings.py > /dev/null
	git diff --exit-code -- '**/RESULTS.json' '**/MEASUREMENTS.json' \
	  '**/ERROR-ANALYSIS.json' '**/stage*.json'

## Regenerate the article's figure regions from the archived run pairs, then fail on any drift.
figures:
	$(PYTHON) tools/article_figures.py
	git diff --exit-code -- article.md evidence/fleet-routing/RESULTS.md

## Refuse a capability declaration the measurements do not support. Exit code is the violation count.
gate:
	$(PYTHON) tools/parity_gate.py

## The gate's own tests: twelve throwaway repositories, each one a way to pass for the wrong reason.
gate-tests:
	$(PYTHON) tools/test_parity_gate.py

## Every figure the article states about the catalog, the download snapshot and the walkthrough is
## still derivable from the artifact it came from. These sections are curated prose rather than
## generated regions, so they are checked instead of rewritten.
derived:
	$(PYTHON) tools/catalog_stats.py --check
	$(PYTHON) tools/downloads_table.py --check
	$(PYTHON) tools/walkthrough_record.py --check

## Snippets, diagrams and regions in the prose match their sources.
article:
	$(PYTHON) tools/sync_article.py --check

## The checks that need a JVM, the local weights, or a provider key. Not run in CI.
measured:
	bash tools/check_grounding_guard.sh
