#!/usr/bin/env python3
"""Generate the article's figure regions from the committed logs.

Every table and every numeric sentence in the comparison sections is produced here and written
between `<!-- figures:NAME -->` markers in article.md. The prose that carries a number lives in
this file for one reason: the article was wrong for several revisions because a re-measurement
refreshed the quoted output blocks while the sentences around them still described the previous
run. A number that cannot drift is a number nobody types twice.

Parsing is reused from derive_fleet_figures, so both tools read the logs the same way.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import derive_fleet_figures as d
from fleet_logs import latest_pair

ROOT = Path(__file__).resolve().parent.parent
ARTICLE = ROOT / "article.md"
RUNS = ROOT / "evidence/fleet-routing/runs"


HEARTBEATS = frozenset({"ping", "still there?", "ok"})


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


def _count(values: set[int]) -> str:
    """One spelled count, or a refusal: two archived pairs that disagree are two fleets."""
    if len(values) != 1:
        raise SystemExit(f"the archived pairs disagree about a count: {sorted(values)}")
    only = next(iter(values))
    return WORDS.get(only, str(only))


def boundary_counts(routed: str) -> tuple[int, int, int, int]:
    """(stayed, total, left, left while a local arm answered), from the demo's own line.

    Computed by the demo and parsed here rather than recomputed from the per-prompt table, because
    the two answers diverged the moment the decision arm could escalate: the router's selected
    model for that prompt is local, and the prompt still sent a customer's ticket to a provider.
    One place computes it; this reads it.
    """
    match = re.search(
        r"(\d+) of (\d+) prompts sent no text off this machine; (\d+) did, (\d+) of them while a"
        r" local arm answered", routed)
    if not match:
        raise SystemExit(
            "the routed log has no data-boundary line; it predates the escalation ledger and its "
            "prompt counts cannot be read safely")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def escalation_note(routed: str) -> str:
    """How many decision questions escalated, and below what confidence, from the demo's own line.

    The count used to be described rather than read ("the questions it was not confident about"),
    which is the shape of sentence that survives a threshold change without noticing it. The demo
    prints both numbers; this reads them, so a fleet shipped with a different default rewrites the
    prose instead of outliving it.
    """
    match = re.search(
        r"the decision arm escalated (\d+) of its questions below confidence ([\d.]+)", routed)
    if not match:
        raise SystemExit(
            "the routed log has no escalation line, yet a prompt left while a local arm answered; "
            "the two cannot both be true of the same run")
    count, threshold = match.groups()
    questions = "question" if count == "1" else "questions"
    return f"the decision arm escalated {count} of its {questions} below confidence {threshold}"


def provider_declarations() -> list[dict]:
    """Each remote candidate's id, prices, context window and capabilities, from fleet.java.

    The paragraph that describes the remotes used to carry their windows as hand-typed prose, and
    said "200k, 400k and 1M" for months after the premium window was corrected to 272,000 in the
    code -- against the provider's own refusal message. Six-figure numbers in the article are
    checked against the sources, but "400k" is not a six-figure number to a regular expression.
    """
    source = (ROOT / "code/fleet.java").read_text()
    constants = dict(re.findall(r'static final String (\w+) = "([^"]+)";', source))
    numbers = dict(re.findall(r"static final double (\w+) = ([\d.]+);", source))
    start = source.index("// region: providers")
    region = source[start : source.index("// endregion", start)]
    found = []
    for block in re.split(r"ModelCandidate\.builder\(", region)[1:]:
        name = block[: block.index(")")]
        window = re.search(r"\.contextWindow\(([\d_]+)\)", block)
        prices = re.search(r"\.costPerMillionTokens\((\w+), (\w+)\)", block)
        caps = re.search(r"\.capabilities\(Set\.of\(([^)]*)\)\)", block)
        if not (window and prices and caps):
            raise SystemExit(f"remote candidate {name} declares no window, prices or capabilities")
        tier = re.search(r"\.pricingTier\(([\d_]+), (\w+), (\w+)\)", block)
        found.append({
            "id": constants.get(name, name),
            "window": int(window.group(1).replace("_", "")),
            "in": float(numbers[prices.group(1)]),
            "out": float(numbers[prices.group(2)]),
            "capabilities": sorted(c.strip().strip('"') for c in caps.group(1).split(",")),
            # The high-volume tier, if the candidate declares one, with its literal values: the
            # article inlines them into a sentence (`.pricingTier(100_001, 0.50, 2.50)`) where the
            # source carries named constants, so the two have to be checked against each other.
            "tier": (int(tier.group(1).replace("_", "")),
                     float(numbers[tier.group(2)]),
                     float(numbers[tier.group(3)])) if tier else None,
        })
    return found


def declared_providers() -> int:
    """How many remote providers the fleet declares, read from its own providers region.

    Not how many it billed. The ledger counts providers that were charged, and a run where the
    long-document prompt never reaches the third one would label a three-provider fleet as a
    two-provider fleet -- which is a statement about one afternoon's routing, printed where a
    reader looks for the fleet's composition.
    """
    source = (ROOT / "code/fleet.java").read_text()
    start = source.index("// region: providers")
    region = source[start : source.index("// endregion", start)]
    declared = len(re.findall(r"\.costPerMillionTokens\(", region))
    if not declared:
        raise SystemExit("no remote candidates found in fleet.java's providers region")
    return declared


def thousands(n: int) -> str:
    return f"{n:,}"


def money(value: Decimal) -> str:
    return f"${value:.6f}"


def baseline_region(routed: str, remote: str) -> str:
    """What the no-router arm costs and where that cost sits."""
    far = d.all_remote_rows(remote)
    ar_in, ar_out, in_price, out_price, ar_cost = d.all_remote_total(remote)
    wall = int(re.search(r"conversation wall clock: (\d+) ms", remote).group(1))

    text, big_in, big_out, big_ms = max(far, key=lambda r: r[1])
    big_input_cost = Decimal(big_in) * in_price / Decimal(1_000_000)

    # The heartbeats are named here so that renaming them in the demo breaks this generator
    # instead of leaving three stale latencies in the article.
    beats = {t: ms for t, _in, _out, ms in far if t in HEARTBEATS}
    missing = HEARTBEATS - set(beats)
    if missing:
        raise SystemExit(f"all-remote table has no row for {sorted(missing)}")
    beat_ms = ", ".join(f"{beats[t]:,} ms" for t in sorted(beats, key=lambda t: beats[t]))

    return "\n".join([
        f"Every prompt answered, in {wall / 1000:.0f} seconds, for **{money(ar_cost)}**.",
        "",
        f"Two things in that table do the damage. The appendix is **{thousands(big_in)} input "
        f"tokens**, and at the declared rate that one prompt is **{money(big_input_cost)}** — "
        f"{big_input_cost / ar_cost * 100:.0f}% of the bill, paid to a frontier model to compress a "
        f"document into two sentences. And the {len(beats)} heartbeats, whose only correct answer "
        f"is \"still here\", took {beat_ms}, because a network round trip costs most of a second "
        "whatever you ask for.",
    ])


def cost_region(routed: str, remote: str) -> str:
    providers, routed_cost = d.ledger(routed)
    rows = d.routed_prompt_rows(routed)
    far = d.all_remote_rows(remote)
    ar_in, ar_out, in_price, out_price, ar_cost = d.all_remote_total(remote)

    local_idx = [i for i, r in enumerate(rows) if r[1] not in set(providers)]
    local_out = sum(far[i][2] for i in local_idx)
    local_in = sum(far[i][1] for i in local_idx)
    local_cost = (Decimal(local_in) * in_price + Decimal(local_out) * out_price) / Decimal(1_000_000)

    routed_in = sum(p[0] for p in providers.values())
    routed_out = sum(p[1] for p in providers.values())
    pct = (ar_cost - routed_cost) / ar_cost * 100
    factor = ar_cost / routed_cost

    # The cheap provider is the one that read the appendix: the routed ledger row with the most
    # input tokens. Priced again at the premium provider's declared rate, it is the whole saving.
    bulk_id, (bulk_in, bulk_out, bulk_cost) = max(providers.items(), key=lambda kv: kv[1][0])
    bulk_premium = (Decimal(bulk_in) * in_price + Decimal(bulk_out) * out_price) / Decimal(1_000_000)
    premium_id = re.search(r"had every prompt gone to (\S+):", routed).group(1)

    escalated = [
        (text, rows[i][1]) for i, (text, *_rest) in enumerate(far) if rows[i][1] in set(providers)
    ]
    where = ", ".join(f"*{t if len(t) <= 44 else t[:43].rstrip() + chr(8230)}* to {m}"
                      for t, m in escalated)

    return "\n".join([
        (lambda stayed, total, left, mixed:
         f"{stayed} of the {total} prompts sent no text off this machine. The "
         f"{len(escalated)} the router sent to a provider did not go to the same one: {where} — "
         "and that second choice is most of the story."
         + (f" {'A further prompt' if mixed == 1 else f'A further {mixed} prompts'} left while a "
            f"local arm answered: {escalation_note(routed)}."
            if mixed else ""))(*boundary_counts(routed)),
        "",
        "| | input tokens | completion tokens | cost |",
        "| --- | --- | --- | --- |",
        f"| Every prompt through {premium_id} | {thousands(ar_in)} | {thousands(ar_out)} | "
        f"**{money(ar_cost)}** |",
        f"| Routed across the fleet | {thousands(routed_in)} | {thousands(routed_out)} | "
        f"**{money(routed_cost)}** |",
        "",
        f"**{pct:.1f}% less, a factor of {factor:.2f}.** Note where it does *not* come from. The "
        f"{len(local_idx)} prompts answered locally would have cost {money(local_cost)} on "
        f"{premium_id} — **{local_cost / ar_cost * 100:.1f}%** of the bill. Keeping them local is "
        "almost free either way.",
        "",
        f"The saving is one decision: the same {thousands(bulk_in)}-token document cost "
        f"**{money(bulk_cost)}** at {bulk_id}'s declared rate instead of **{money(bulk_premium)}** "
        f"at {premium_id}'s. Both providers can hold it; one costs "
        f"{bulk_premium / bulk_cost:.1f} times less to read it.",
    ])


def per_prompt_region(routed: str, remote: str) -> str:
    rows = d.routed_prompt_rows(routed)
    far = d.all_remote_rows(remote)
    providers = set(d.ledger(routed)[0])

    out = ["| prompt | no router | routed | | destination |", "| --- | --- | --- | --- | --- |"]
    for (text, _, _, base_ms), (_, selected, _, routed_ms) in zip(far, rows):
        ratio = base_ms / routed_ms if routed_ms else 0
        if 1 / 1.15 < ratio < 1.15:
            verdict = "level"
        elif ratio > 1:
            verdict = f"{ratio:.1f}× faster"
        else:
            verdict = f"{1 / ratio:.1f}× *slower*"
        bold_base, bold_routed = f"{base_ms:,} ms", f"{routed_ms:,} ms"
        if ratio > 1.15:
            bold_routed = f"**{bold_routed}**"
        elif ratio < 1 / 1.15:
            bold_base = f"**{bold_base}**"
        where = "local" if selected not in providers else selected
        label = text if len(text) <= 46 else text[:45].rstrip() + "…"
        out.append(f"| {label} | {bold_base} | {bold_routed} | {verdict} | {where} |")

    # Which of those rows mean anything across runs, and which are one afternoon. Computed over
    # every archived pair, because the first version of this paragraph described a single run's
    # ordering as though it were the shape of the workload, and the next run reversed half of it.
    across = per_prompt_across_pairs()
    beats = [r for label, r in across.items() if label in HEARTBEATS]
    beat_lo = min(min(r) for r in beats)
    beat_hi = max(max(r) for r in beats)
    flipped = [label for label, ratios in across.items() if min(ratios) < 1 <= max(ratios)]
    n = len(next(iter(across.values())))

    out += [
        "",
        f"One row holds across all {n} archived pairs: a heartbeat is answered locally "
        f"**{beat_lo:.1f}× to {beat_hi:.1f}× faster** than a network round trip can answer it at "
        "all. Nothing a hosted model does is quick when the speed of light is in the way, and in a "
        "real deployment this row is most of the traffic.",
    ]
    if flipped:
        out.append("")
        out.append(
            f"The rest of the table is one afternoon: **{len(flipped)} of the {len(across)} "
            "prompts** changed which arm was faster between pairs, so the per-prompt ordering is "
            "not a property of the fleet either. What is stable is where each prompt went and what "
            "it cost, which is what the policy actually decides."
        )
    return "\n".join(out)


def per_prompt_across_pairs() -> dict[str, list[float]]:
    """prompt -> no-router/routed latency ratio, one entry per archived pair."""
    ratios: dict[str, list[float]] = {}
    for stamp, *_ in pairs():
        routed = (RUNS / f"{stamp}-routed.log").read_text()
        remote = (RUNS / f"{stamp}-all-remote.log").read_text()
        rows = d.routed_prompt_rows(routed)
        far = d.all_remote_rows(remote)
        if len(rows) != len(far):
            raise SystemExit(f"{stamp}: arms disagree on prompt count")
        for (label, _, _, base_ms), (_, _, _, routed_ms) in zip(far, rows):
            ratios.setdefault(label, []).append(base_ms / routed_ms)
    counts = {len(v) for v in ratios.values()}
    if len(counts) != 1:
        raise SystemExit("archived pairs do not all carry the same prompts")
    return ratios


def current_pin() -> str:
    """The ModelJars version the demo is pinned to right now."""
    source = (ROOT / "code/fleet.java").read_text()
    return re.search(r"//DEPS org\.modeljars:modeljars:(\S+)", source).group(1)


def pairs() -> list[tuple[str, int, int, int]]:
    """(stamp, routed wall, no-router wall, local ms) for every archived pair on the current pin.

    A pair measured before a runtime change cannot be averaged with one measured after it. The
    0.1.62 decision change moved the routed arm by seconds, so the harness records each pair's
    pins and this reads only the pairs that match what the demo resolves today.
    """
    pin = current_pin()
    found = []
    for routed in sorted(RUNS.glob("*-routed.log")):
        meta = routed.with_name(routed.name[:16] + ".meta")
        if not meta.exists() or f"modeljars:{pin}" not in meta.read_text():
            continue
        base = routed.with_name(routed.name.replace("-routed", "-all-remote"))
        if not base.exists():
            continue
        rt, bt = routed.read_text(), base.read_text()
        r = re.search(r"conversation wall clock: (\d+) ms", rt)
        b = re.search(r"conversation wall clock: (\d+) ms", bt)
        if not (r and b):
            continue
        local = sum(
            total for model, (_, total, _) in d.timing_rows(rt).items()
            if not model.startswith(("gpt-", "claude-"))
        )
        found.append((routed.name[:16], int(r.group(1)), int(b.group(1)), local))
    return found


def variance_region() -> str:
    found = pairs()
    if not found:
        raise SystemExit("no archived run pairs in evidence/fleet-routing/runs")

    ratios = [r / b for _, r, b, _ in found]
    bases = [b for _, _, b, _ in found]
    locals_ = [local for *_, local in found]
    remotes = [r - local for _, r, _, local in found]
    savings = [cost_factor(stamp) for stamp, *_ in found]
    appendix = [heaviest_prompt_ms(stamp) for stamp, *_ in found]

    lines = [
        "| run (UTC) | routed | no router | latency ratio | cost factor |",
        "| --- | --- | --- | --- | --- |",
    ]
    for (stamp, r, b, _local), saving in zip(found, savings):
        lines.append(f"| `{stamp}` | {r:,} ms | {b:,} ms | {r / b:.2f}× | {saving:.2f}× cheaper |")
    lines += [
        "",
        f"Across **{len(found)} measured pair{'s' if len(found) != 1 else ''}** — same code, same "
        f"prompts, same machine, all archived under "
        "[`evidence/fleet-routing/runs/`](evidence/fleet-routing/runs) — the latency ratio moved "
        f"from **{min(ratios):.2f}× to {max(ratios):.2f}×** (median "
        f"{statistics.median(ratios):.2f}×) while the cost factor moved from "
        f"**{min(savings):.2f}× to {max(savings):.2f}×**. One of those is a property of the fleet; "
        "the other is a property of the provider's queue on the day. Which is which:",
        "",
        f"- the no-router arm's wall clock ranged over **{max(bases) / min(bases):.2f}×** "
        f"({min(bases):,} ms to {max(bases):,} ms)",
        f"- the routed arm's remote portion ranged over **{max(remotes) / min(remotes):.2f}×** "
        f"({min(remotes):,} ms to {max(remotes):,} ms)",
        f"- the routed arm's local portion ranged over **{max(locals_) / min(locals_):.2f}×** "
        f"({min(locals_):,} ms to {max(locals_):,} ms)",
        f"- the appendix prompt alone, byte for byte identical every run, came back in "
        f"{min(appendix):,} ms at best and {max(appendix):,} ms at worst — "
        f"**{max(appendix) / min(appendix):.2f}×** on one call to one provider",
    ]
    return "\n".join(lines)


def heaviest_prompt_ms(stamp: str) -> int:
    """Latency of the largest prompt in the no-router arm, where nothing else can explain it."""
    remote = (RUNS / f"{stamp}-all-remote.log").read_text()
    return max(d.all_remote_rows(remote), key=lambda r: r[1])[3]


def cost_factor(stamp: str) -> Decimal:
    """all-remote bill / routed bill for one archived pair."""
    routed = (RUNS / f"{stamp}-routed.log").read_text()
    remote = (RUNS / f"{stamp}-all-remote.log").read_text()
    return d.all_remote_total(remote)[4] / d.ledger(routed)[1]


def grouping_region(routed: str, remote: str) -> str:
    """What a batch of typed decisions costs, before and after the 0.1.62 runtime change.

    Both releases are measured on a host that is doing nothing else, twice each, because a batch
    of decisions is seconds of local compute and this workstation's own editor moves that by more
    than the change does. Every pass is read here rather than one of them, so a figure that moved
    between passes is printed as the range it was.
    """
    runs: dict[str, list[dict[str, int]]] = {}
    for version in ("0.1.61", "0.1.62"):
        logs = sorted((ROOT / "evidence/harriet-decisions").glob(
            f"grouping-{version.replace('.', '')}-pass*.log"))
        if not logs:
            raise SystemExit(
                f"no probe logs for {version}: run tools/measure_on_isolated_host.sh --confirm")
        runs[version] = [{
            m.group(1).strip(): int(m.group(2))
            for m in re.finditer(
                r"^(\D.*?)\s{2,}(\d+)\s+\d+(?:\s+\d+)?\s*$", log.read_text(), re.M)
            if not m.group(1).startswith(("BATCH", "DISCARDED"))
        } for log in logs]

    def span(version: str, key: str) -> str:
        values = sorted(pass_[key] for pass_ in runs[version])
        return f"{values[0]:,} ms" if values[0] == values[-1] else f"{values[0]:,}–{values[-1]:,} ms"

    def extra(version: str, prefix: str) -> list[float]:
        return sorted((pass_[f"{prefix}, 3 questions"] - pass_[f"{prefix}, 1 question"]) / 2
                      for pass_ in runs[version])

    passes = min(len(v) for v in runs.values())
    columns = [(shape, version) for shape in ("one shared rubric", "three different rubrics")
               for version in runs]
    out = ["| questions about one ticket | " + " | ".join(
        f"{shape}, {version}" for shape, version in columns) + " |",
        "| --- | " + " | ".join("---" for _ in columns) + " |"]
    for count in (1, 2, 3):
        cells = []
        for shape, version in columns:
            prefix = "one rubric" if shape.startswith("one") else "three rubrics"
            cells.append(span(version, f"{prefix}, {count} question{'s' if count != 1 else ''}"))
        out.append(f"| {count} | " + " | ".join(cells) + " |")

    mixed_before, mixed_after = extra("0.1.61", "three rubrics"), extra("0.1.62", "three rubrics")
    shared_before = extra("0.1.61", "one rubric")
    shared_after = extra("0.1.62", "one rubric")
    out += [
        "",
        f"Each build was run {passes} times and the range is what moved; the first question costs "
        "what reading the ticket costs and no build changes it. What the next two cost is the "
        f"finding. On 0.1.61 they cost **{mixed_before[0]:,.0f}–{mixed_before[-1]:,.0f} ms** each "
        f"when the rubrics differ against **{shared_before[0]:,.0f}–{shared_before[-1]:,.0f} ms** "
        "when they are shared, because a question whose rubric differed read the whole ticket "
        "again.",
        "",
        f"0.1.62 moves the resumption point behind the rubric when the rubrics differ, so such a "
        f"question reads only its own rules: **{mixed_after[0]:,.0f}–{mixed_after[-1]:,.0f} ms** "
        f"each, **{mixed_before[0] / mixed_after[-1]:.1f}× to "
        f"{mixed_before[-1] / mixed_after[0]:.1f}× cheaper**, with every measured answer identical "
        f"and the live heap unchanged. A batch that shares one rubric is untouched "
        f"({shared_after[0]:,.0f}–{shared_after[-1]:,.0f} ms per extra question) and is still the "
        "cheapest shape there is.",
    ]
    return "\n".join(out)


def provider_latency_region(routed: str, remote: str) -> str:
    """One prompt, sent repeatedly to each provider: what moves and what does not."""
    log = ROOT / "evidence/fleet-routing/appendix-providers.log"
    samples: dict[str, list[tuple[int, Decimal]]] = {}
    for line in log.read_text().splitlines():
        m = re.match(r"^(\S+)\s+run\d+\s+(\d+) ms\s+(\d+) in \+\s*(\d+) out\s+\$([\d.]+)", line)
        if m:
            samples.setdefault(m.group(1), []).append((int(m.group(2)), Decimal(m.group(5))))
    if not samples:
        raise SystemExit(f"{log.name}: no samples parsed")

    out = ["| provider | n | fastest | median | slowest | spread | cost of the same input |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for model, rows in samples.items():
        ms = sorted(r[0] for r in rows)
        costs = [r[1] for r in rows]
        median = ms[len(ms) // 2] if len(ms) % 2 else (ms[len(ms) // 2 - 1] + ms[len(ms) // 2]) // 2
        out.append(
            f"| {model} | {len(ms)} | {min(ms):,} ms | {median:,} ms | {max(ms):,} ms | "
            f"**{max(ms) / min(ms):.1f}×** | {money(min(costs))} to {money(max(costs))} |")

    spreads = [max(r[0] for r in rows) / min(r[0] for r in rows) for rows in samples.values()]
    return "\n".join(out + [
        "",
        f"The same prompt, the same declared model, {min(len(v) for v in samples.values())} calls "
        f"each: latency spread **{min(spreads):.1f}× to {max(spreads):.1f}×**, while the bill moved "
        "in the sixth decimal place — the few completion tokens the model chose to emit. A hosted "
        "model's price is something you can quote. Its latency is something you can only sample, "
        "and this article says how many times it was sampled wherever it quotes one.",
    ])


HEARTBEAT_ORDER = ("ping", "still there?", "ok")


def gate_report() -> dict:
    """The parity gate's rows and violations, as the gate itself computes them."""
    gate = ROOT / "tools/parity_gate.py"
    finished = subprocess.run([sys.executable, str(gate), "--json"],
                              capture_output=True, text=True, cwd=ROOT)
    if not finished.stdout.strip():
        raise SystemExit(f"parity_gate.py --json printed nothing: {finished.stderr.strip()}")
    return json.loads(finished.stdout)


def accuracy_cell(side: str) -> str:
    """One cell of the summary table's accuracy row, read from the gate.

    It used to read the first experiment's four stages directly, which stopped being the whole
    truth the moment the fleet's arms changed in response to them: the 1B grounding arm it
    reported is not the arm this fleet ships. The gate knows which measurement belongs to which
    declaration, so the cell asks the gate.
    """
    report = gate_report()
    scored = [r for r in report["rows"] if r["delta"] not in (None, "-")]
    if not scored:
        return "**not measured**"
    deltas = sorted(float(r["delta"]) for r in scored)
    references = sorted(float(r["against"]) for r in scored)
    capabilities = {r["capability"] for r in scored}
    if side != "routed":
        return (f"the reference: **{references[0]:.0f} to {references[-1]:.0f}** "
                "depending on the task")
    unsupported = len(report["violations"])
    worst, best = deltas[0], deltas[-1]
    shape = (f"**{worst:+.1f} to {best:+.1f} points** against gpt-5.1 on "
             f"{len(scored)} public datasets across {len(capabilities)} declared "
             f"{'capability' if len(capabilities) == 1 else 'capabilities'}")
    if unsupported:
        return (shape + f", and **{unsupported} declaration"
                + ("" if unsupported == 1 else "s")
                + " the measurements do not support** — see below")
    return shape + ", every declaration checked — see below"


def summary_region(routed: str, remote: str) -> str:
    """The whole comparison on one screen, derived from every archived pair on the current pin.

    Written as a range per row rather than a single reading, because one of these rows is a
    property of the fleet and the rest are a property of the afternoon, and a table of single
    numbers hides which is which. The accuracy row is deliberately empty: neither arm's answers
    were scored, and a cost-and-latency harness cannot be stretched into a quality measurement.
    """
    found = pairs()
    if not found:
        raise SystemExit("no archived pairs on the current pin")

    costs, base_costs, factors, walls, base_walls = [], [], [], [], []
    locals_, remotes, beats, startups, local_answered, total_prompts = [], [], [], [], set(), set()
    appendix, local_token_share, local_models, providers_seen = [], [], set(), set()
    stayed_counts: set[int] = set()

    for stamp, routed_ms, base_ms, local in found:
        rt = (RUNS / f"{stamp}-routed.log").read_text()
        bt = (RUNS / f"{stamp}-all-remote.log").read_text()
        providers, routed_cost = d.ledger(rt)
        providers_seen.add(len(set(providers)))
        _, _, _, _, base_cost = d.all_remote_total(bt)
        rows, far = d.routed_prompt_rows(rt), d.all_remote_rows(bt)

        costs.append(routed_cost)
        base_costs.append(base_cost)
        factors.append(base_cost / routed_cost)
        walls.append(routed_ms)
        base_walls.append(base_ms)
        locals_.append(local)
        remotes.append(routed_ms - local)
        startup = re.search(r"one-off load of the (\d+) local models: (\d+) ms", rt)
        if not startup:
            raise SystemExit(f"{stamp}: the routed log has no startup line this tool can read")
        local_models.add(int(startup.group(1)))
        startups.append(int(startup.group(2)))

        escalated = {i for i, row in enumerate(rows) if row[1] in set(providers)}
        local_answered.add(len(rows) - len(escalated))
        stayed, total, _left, _mixed = boundary_counts(rt)
        stayed_counts.add(stayed)
        total_prompts.add(total)
        beats += [(far[i][3], rows[i][3]) for i, row in enumerate(far)
                  if row[0] in HEARTBEAT_ORDER]
        appendix.append(max(far, key=lambda r: r[1])[3])
        share = re.search(r"input tokens were routed off this machine \(([\d.]+)%\)", rt)
        if share:
            local_token_share.append(float(share.group(1)))

    def span(values, unit="ms", fmt=",.0f"):
        low, high = min(values), max(values)
        if low == high:
            return f"{low:{fmt}} {unit}".strip()
        return f"{low:{fmt}}–{high:{fmt}} {unit}".strip()

    def money_span(values):
        low, high = min(values), max(values)
        return money(low) if low == high else f"{money(low)}–{money(high)}"

    beat_ratios = [b / r for b, r in beats]
    premium = re.search(r"had every prompt gone to (\S+):", routed).group(1)

    rows_out = [
        ("**Cost, all " + str(next(iter(total_prompts))) + " prompts**",
         f"**{money_span(costs)}**", money_span(base_costs)),
        ("Cost factor",
         f"**{min(factors):.2f}× to {max(factors):.2f}× cheaper**, and steady: the prompts fix the "
         "token counts", "—"),
        ("**Wall clock, warm**", f"**{span(walls)}**", span(base_walls)),
        ("Latency ratio",
         f"**{min(walls[i] / base_walls[i] for i in range(len(walls))):.2f}× to "
         f"{max(walls[i] / base_walls[i] for i in range(len(walls))):.2f}×** over "
         f"{len(found)} pairs" + (", routed faster in one of them"
             if any(walls[i] < base_walls[i] for i in range(len(walls))) else ""), "—"),
        ("Latency you can rely on",
         f"local portion {span(locals_)}, a **{max(locals_) / min(locals_):.2f}× spread**",
         f"all of it is the other kind: the routed arm's own remote portion spans "
         f"**{max(remotes) / min(remotes):.2f}×**, and one byte-identical provider call spans "
         f"**{max(appendix) / min(appendix):.2f}×**"),
        (f"The {len(HEARTBEAT_ORDER)} heartbeats",
         f"**{span([r for _, r in beats])}**",
         f"{span([b for b, _ in beats])} — {min(beat_ratios):.1f}× to {max(beat_ratios):.1f}× slower"),
        ("Startup",
         f"**{span(startups)}** to load {_count(local_models)} local models, paid once, excluded "
         "from every per-request figure above", "none"),
        ("Data boundary",
         f"**{next(iter(stayed_counts))} of {next(iter(total_prompts))} prompts sent no text off "
         f"the machine**; by token count {max(local_token_share):.1f}% still did, because the one "
         "appendix dwarfs the other nine prompts",
         f"every prompt and every token goes to {premium}"),
        ("**Accuracy**", accuracy_cell("routed"), accuracy_cell("allApi")),
    ]

    return "\n".join(
        [f"| | Routed fleet — {_count(local_models)} local models and "
         f"{WORDS.get(declared_providers(), declared_providers())} providers | "
         f"Every prompt to {premium} |",
         "| --- | --- | --- |"]
        + [f"| {axis} | {left} | {right} |" for axis, left, right in rows_out])


def accuracy_region(routed: str, remote: str) -> str:
    """The accuracy row, from experiments/routing-accuracy/RESULTS.json.

    This row said "not measured" until there was something to put in it. What went in is not what
    the routing argument assumed, which is the reason the experiment was run rather than reasoned
    about.
    """
    results = ROOT / "experiments/routing-accuracy/RESULTS.json"
    if not results.exists():
        raise SystemExit("experiments/routing-accuracy/RESULTS.json is missing: run score.py")
    stages = json.loads(results.read_text())["stages"]
    if not stages:
        raise SystemExit("RESULTS.json has no scored stages")

    names = {
        "qa/squad2": ("SQuAD v2 dev, half of it unanswerable", "exact match"),
        "qa/hotpotqa": ("HotpotQA distractor, ten paragraphs per question", "exact match"),
        "decide/snips": ("SNIPS 2017, seven intents", "label accuracy"),
        "decide/trec": ("TREC coarse, six classes", "label accuracy"),
    }
    # "the arm this fleet had" rather than "routed": these are the arms the walkthrough shipped
    # before this measurement, and two of them were replaced because of it. Calling the column
    # `routed` would now name a configuration that no longer exists.
    out = ["| public dataset | metric | the local arm this fleet had | every prompt to gpt-5.1 |"
           " difference |",
           "| --- | --- | --- | --- | --- |"]
    deltas = []
    for key, (label, metric) in names.items():
        stage = stages.get(key)
        if not stage:
            continue
        low, high = stage["ci95"]
        deltas.append(stage["delta"])
        out.append(f"| {label} (n={stage['n']}) | {metric} | **{stage['routed']:.1f}** | "
                   f"**{stage['allApi']:.1f}** | {stage['delta']:+.1f} [{low:+.0f}, {high:+.0f}] |")

    split = stages.get("qa/squad2", {}).get("split", {})
    if split:
        answerable = split.get("answerable/routed", {})
        answerable_api = split.get("answerable/allApi", {})
        unanswerable = split.get("unanswerable/routed", {})
        unanswerable_api = split.get("unanswerable/allApi", {})
        out += [
            "",
            f"Every dataset rejects it, by {abs(max(deltas)):.0f} to {abs(min(deltas)):.0f} points, "
            "under a threshold fixed before the run. The aggregate hides where the loss is, and the "
            "split is the finding: on SQuAD's answerable half the 1B model scores "
            f"**{answerable.get('exactMatch', 0):.1f}** against the frontier model's "
            f"**{answerable_api.get('exactMatch', 0):.1f}** — a tie on extracting an answer from "
            "one short passage. On the unanswerable half it scores "
            f"**{unanswerable.get('exactMatch', 0):.1f}** against "
            f"**{unanswerable_api.get('exactMatch', 0):.1f}**, because it declined "
            f"**{unanswerable.get('abstained', 0)} times out of {unanswerable.get('n', 0)}** while "
            f"gpt-5.1 declined {unanswerable_api.get('abstained', 0)}. HotpotQA, which has no "
            "unanswerable questions, isolates the rest: ten paragraphs and two-hop answers cost "
            f"{abs(stages['qa/hotpotqa']['delta']):.0f} points with no abstention involved.",
        ]
    return "\n".join(out)


def verify_prose(article: str, routed: str) -> None:
    """Fail on a six-figure number in the prose that no committed artifact supports.

    A handful of figures belong in sentences rather than tables -- the appendix's size is the one
    that carries an argument -- and they cannot be generated in place without mangling the
    sentence. So they are checked instead, against every number that appears in the committed
    evidence or in the demo's own source. A re-measurement that moves one of them now raises here
    and names it, rather than leaving the prose describing the previous run.

    Six figures and up only: smaller numbers are too common to tell a stale token count from a
    section number, and the figures that have actually drifted in this article were all large.
    """
    rows = d.routed_prompt_rows(routed)
    expected = f"{max(r[2] for r in rows):,}"
    if expected not in article:
        raise SystemExit(f"article.md no longer states the appendix size ({expected} local tokens)")

    supported = set()
    sources = list((ROOT / "evidence").rglob("*")) + list((ROOT / "code").rglob("*.java"))
    for path in sources:
        if not path.is_file() or path.suffix in {".png", ".svg", ".gguf"}:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for raw in re.findall(r"\d[\d_,]{4,}", text):
            digits = raw.replace("_", "").replace(",", "")
            if digits.isdigit():
                supported.add(int(digits))

    # Whole comma-grouped numbers only: matching a fragment reads the tail of 5,973,624 as its
    # own figure and reports a download count as an unsupported token count.
    stale = sorted({
        m.group(0) for m in re.finditer(r"(?<![\d,])\d{1,3}(?:,\d{3})+(?![\d,])", article)
        if int(m.group(0).replace(",", "")) >= 100_000
        and int(m.group(0).replace(",", "")) not in supported
    })
    if stale:
        raise SystemExit(
            "article.md states six-figure numbers that no file under evidence/ or code/ contains: "
            f"{stale}")

    # The decision arm's quoted probabilities and confidences, which are small numbers and
    # therefore invisible to the check above. They are exactly the kind that drift: the article
    # quotes `true p=0.920 confidence=0.60` from a `decisions.java` log, and a runtime change moves
    # the third decimal. Each one has to appear in some committed log, in the same shape.
    quoted = {m.group(0) for m in re.finditer(r"(?:p|confidence|c)=0\.\d+", article)}
    logged = set()
    for path in (ROOT / "evidence").rglob("*.log"):
        text = path.read_text(errors="ignore")
        for match in re.finditer(r"(p|confidence|c)=(0\.\d+)", text):
            logged.add(f"{match.group(1)}={match.group(2)}")
            # `p=0.920` in the prose against `p=0.920123` in the log is the same measurement
            # printed to fewer places, so a prefix of a logged value counts as logged.
            for places in range(2, len(match.group(2))):
                logged.add(f"{match.group(1)}={match.group(2)[:places + 1]}")
    unsupported = sorted(quoted - logged)
    if unsupported:
        raise SystemExit(
            "article.md quotes decision figures that no log under evidence/ contains: "
            f"{unsupported}")

    # Provider rates, which are small numbers and therefore invisible to the six-figure check as
    # well. The article quotes them per vendor as `$1.25/$10.00 per million`; each pair has to be a
    # pair some remote candidate actually declares, or a price edit in fleet.java moves the bill
    # without moving the sentence that explains it.
    declared = provider_declarations()
    declared_rates = {(d_["in"], d_["out"]) for d_ in declared}
    declared_rates |= {(d_["tier"][1], d_["tier"][2]) for d_ in declared if d_["tier"]}
    for match in re.finditer(r"\$(\d+\.\d\d)/\$(\d+\.\d\d)", article):
        pair = (float(match.group(1)), float(match.group(2)))
        if pair not in declared_rates:
            raise SystemExit(
                f"article.md quotes a provider rate of {match.group(0)}, which no candidate in "
                f"code/fleet.java declares; declared: {sorted(declared_rates)}")

    # The inlined tier call, which the article writes with literals for readability.
    for d_ in declared:
        if not d_["tier"]:
            continue
        threshold, tier_in, tier_out = d_["tier"]
        rendered = f".pricingTier({threshold:_}, {tier_in:.2f}, {tier_out:.2f})"
        if rendered not in article:
            raise SystemExit(
                f"article.md does not state {d_['id']}'s declared tier as `{rendered}`")


def conclusion_region(routed: str, remote: str) -> str:
    """The closing paragraph's numbers, from the archived pairs and from the gate.

    The conclusion used to restate figures from the tables above it in prose, which is how a
    conclusion ends up describing a previous run. It states them from the same artifacts now, and
    the declaration count comes from the gate rather than from a count somebody keeps by hand.

    It also used to end "those were the numbers this article had from the start", which is a claim
    about history that nothing here can check -- and re-measuring on the 0.1.65 pins falsified it:
    the routed arm's remote variation went from 1.96x to 5.78x. A generated region may only assert
    what its artifacts support, so it now says which run and which pins the numbers came from.
    """
    found = pairs()
    if not found:
        raise SystemExit("no archived pairs on the current pin")
    factors, locals_, remotes_, local_answered, total_prompts = [], [], [], set(), set()
    for stamp, routed_ms, base_ms, local in found:
        rt = (RUNS / f"{stamp}-routed.log").read_text()
        bt = (RUNS / f"{stamp}-all-remote.log").read_text()
        providers, routed_cost = d.ledger(rt)
        _, _, _, _, base_cost = d.all_remote_total(bt)
        rows = d.routed_prompt_rows(rt)
        factors.append(base_cost / routed_cost)
        locals_.append(local)
        # The routed arm's remote portion, by the same split the variance table uses: the wall
        # clock minus what the local arms spent. The sentence here used to say the remote portion
        # "did not" vary, which is the opposite of what the table above it measures.
        remotes_.append(routed_ms - local)
        escalated = {i for i, row in enumerate(rows) if row[1] in set(providers)}
        stayed, total, _left, _mixed = boundary_counts(rt)
        local_answered.add(stayed)
        total_prompts.add(total)

    report = gate_report()
    checked = len(report["rows"])
    dataset_backed = sum(1 for row in report["rows"] if row["dataset"] != "-")
    unsupported = len(report["violations"])
    supported = "every one of them" if not unsupported else f"{checked - unsupported} of them"

    return (
        f"{next(iter(local_answered))} of {next(iter(total_prompts))} requests in the run above "
        f"sent no text off this machine, the bill came to {min(factors):.2f}× to {max(factors):.2f}× less "
        f"than sending all ten to a frontier model, and across {WORDS[len(found)]} runs of "
        f"identical code the local portion of the wall clock varied by "
        f"{max(locals_) / min(locals_):.2f}× while the remote portion varied by "
        f"{max(remotes_) / min(remotes_):.2f}×. Those are this run's numbers, measured on the pins "
        "this article resolves today.\n\n"
        f"What it did not have was the right to the word *enough*. It does now: {checked} "
        f"declarations are checked -- {dataset_backed} of them against a public dataset, the rest "
        f"against the evidence their basis names -- and {supported} "
        "is backed by a measurement of the model the fleet actually ships"
        + ("." if not unsupported else
           f", with {unsupported} still unsupported and the build red until they are not.")
    )


def measurement_records(experiment: str) -> list[dict]:
    """One experiment's MEASUREMENTS.json, or a failure that names what has not been scored."""
    path = ROOT / "experiments" / experiment / "MEASUREMENTS.json"
    if not path.exists():
        raise SystemExit(f"experiments/{experiment}/MEASUREMENTS.json is missing: run its scorer")
    return json.loads(path.read_text())


def pick(records: list[dict], dataset: str, arm: str) -> dict:
    found = [r for r in records if r["capabilityDataset"] == dataset and r["arm"] == arm]
    if len(found) != 1:
        raise SystemExit(f"{len(found)} measurements of {arm!r} on {dataset}; expected one")
    return found[0]


def confidence_medians(dataset: str) -> tuple[float, float]:
    """The local decision arm's median confidence when it was right and when it was wrong.

    Derived here from the arm's own rows rather than quoted, because this pair of numbers is the
    whole reason the escalation gate can work at all, and a stale pair would be an argument for a
    mechanism the data no longer supports.
    """
    source = ROOT / "experiments/routing-accuracy"
    rows = [json.loads(line) for line
            in (source / f"results-decide-routed-{dataset}.jsonl").read_text().splitlines()
            if line.strip()]
    right = [r["confidence"] for r in rows if r["answer"].strip() == r["gold"]]
    wrong = [r["confidence"] for r in rows if r["answer"].strip() != r["gold"]]
    if not right or not wrong:
        raise SystemExit(f"decide/{dataset}: the routed arm was never right or never wrong")
    return statistics.median(right), statistics.median(wrong)


def escalation_region(routed: str, remote: str) -> str:
    """What the decision arm scores alone, escalating, and not at all, with what escalating cost."""
    records = measurement_records("routing-accuracy")
    datasets = [("snips", "SNIPS 2017, seven intents"), ("trec", "TREC coarse, six classes")]
    gated_arm = {r["arm"] for r in records
                 if r["capabilityDataset"].startswith("decide/") and r["arm"].startswith("gated")}
    if len(gated_arm) != 1:
        raise SystemExit(f"expected one gated arm in the decision stage, found {gated_arm}")
    arm = gated_arm.pop()
    threshold = pick(records, "decide/snips", arm)["thresholds"][0]

    out = ["| public dataset | the local arm alone | the local arm, escalating when unsure |"
           " every decision to gpt-5.1 | escalated | what the escalations cost |",
           "| --- | --- | --- | --- | --- | --- |"]
    for dataset, label in datasets:
        local = pick(records, f"decide/{dataset}", "routed")
        gated = pick(records, f"decide/{dataset}", arm)
        api = pick(records, f"decide/{dataset}", "api")
        low, high = gated["ci95"]
        out.append(
            f"| {label} (n={gated['n']}) | {local['value']:.1f} | **{gated['value']:.1f}** "
            f"({gated['delta']:+.1f} [{low:+.1f}, {high:+.1f}]) | {api['value']:.1f} | "
            f"{gated['escalatedShare']:.0f}% | "
            f"${gated['cost']['dollars']:.4f} against ${api['cost']['dollars']:.4f} |")

    medians = {d: confidence_medians(d) for d, _ in datasets}
    snips = pick(records, "decide/snips", arm)
    trec = pick(records, "decide/trec", arm)
    out += [
        "",
        "Harriet does not answer with a label, it answers with a distribution, and the confidence "
        "it reports separates its own hits from its misses — by a lot on one dataset and a little "
        f"on the other. On SNIPS the median confidence is **{medians['snips'][0]:.3f}** where the "
        f"arm was right and **{medians['snips'][1]:.3f}** where it was wrong; on TREC, "
        f"**{medians['trec'][0]:.3f}** against **{medians['trec'][1]:.3f}**. That separation is "
        "what makes a gate possible at all: the arm can be asked to hand over the questions it is "
        f"unsure about, and below a confidence of {threshold} it does. How much it has to hand "
        "over depends on how wide the separation is, which is why the two escalation rates below "
        "are so far apart. The threshold was chosen on SNIPS and scored on TREC, so the data that "
        "picked it is not the data that justifies it.",
        "",
        f"Escalating {snips['escalatedShare']:.0f}% of the SNIPS decisions takes the arm from "
        f"{pick(records, 'decide/snips', 'routed')['value']:.1f} to **{snips['value']:.1f}**, "
        f"against gpt-5.1's {pick(records, 'decide/snips', 'api')['value']:.1f}. On TREC "
        f"it escalates {trec['escalatedShare']:.0f}% and lands at {trec['value']:.1f} against "
        f"{pick(records, 'decide/trec', 'api')['value']:.1f}. Both are inside the two points this "
        "project requires of a declared capability, and the second is exactly at the edge of it: "
        f"at n=100 the TREC interval still spans {trec['ci95'][0]:+.1f} to {trec['ci95'][1]:+.1f}, "
        "which is a hundred items telling you it cannot resolve two points, and is reported here "
        "rather than rounded into the claim.",
        "",
        "The cost column is the honest part of the mechanism. Parity on these datasets is bought "
        "with provider calls, and the fleet ships with the gate on by default because a "
        "declaration measured with it on is a claim about a fleet that runs with it on. A "
        "deployment that cannot pay for the escalations sets the threshold to zero and keeps a "
        "local-only decision arm that is 16 points behind."
        + ("" if "measured on this arm" in str(snips["cost"]["source"]) else
           " Those dollars come from the all-API arm's measured token counts for the same items: "
           "an escalation sends that arm's prompt byte for byte, and the gated rows were collected "
           "before the harness recorded an escalated call's own usage. `MEASUREMENTS.json` says so "
           "per arm, in a `source` field, rather than leaving a reader to assume."),
    ]
    # What the re-measurement says about the SNIPS margin, read from the threshold experiment's
    # own artifact. The sentence this replaced said the combination "beats either alone", which
    # one run supports and the re-run of the same configuration does not.
    audit = json.loads(
        (ROOT / "experiments/decision-threshold/stage1-simulator.json").read_text())
    rerun = audit["datasets"]["snips"]
    drift = rerun["confidenceDrift"]
    out += [
        "",
        f"The SNIPS margin is the one figure here not to lean on. Composing the same two arms' "
        f"committed rows at the same threshold reproduces TREC exactly and gives "
        f"**{rerun['simulated']['accuracy']:.1f}** on SNIPS against the "
        f"**{rerun['measured']['accuracy']:.1f}** measured — parity with gpt-5.1 rather than two "
        f"points above it — because the local arm's confidence is not reproducible between runs: "
        f"median drift **{drift['median']:.4f}**, and "
        f"**{drift['itemsCrossingShippedThreshold']}** of the hundred items changed side of "
        f"{threshold} between the two runs. The declaration survives either way, since this "
        "project's frontier basis asks for parity within two points and not for a win. What does "
        "not survive is the claim that the arm beats the frontier model on SNIPS, and the "
        "[threshold audit](experiments/decision-threshold/FINDINGS.md) is where that was found.",
    ]
    return "\n".join(out)


def grounding_arm_region(routed: str, remote: str) -> str:
    """What each candidate grounding arm scores, and what the one that wins costs per answer."""
    records = measurement_records("grounding-arm-selection")
    results = json.loads(
        (ROOT / "experiments/grounding-arm-selection/RESULTS.json").read_text())
    names = {"squad2": "SQuAD v2 dev, half of it unanswerable",
             "hotpotqa": "HotpotQA distractor, ten paragraphs per question"}
    arms = {"llama1b": "Llama 3.2 1B", "llama3.1-8b": "Llama 3.1 8B"}

    out = ["| arm | public dataset | exact match | gpt-5.1 | difference | median per answer |"
           " peak heap |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for arm, label in arms.items():
        for dataset, dataset_label in names.items():
            record = pick(records, f"qa/{dataset}", arm)
            low, high = record["ci95"]
            heap = record.get("maxHeapMiB")
            out.append(
                f"| {label} | {dataset_label} (n={record['n']}) | **{record['value']:.1f}** | "
                f"{record['reference']['value']:.1f} | {record['delta']:+.1f} "
                f"[{low:+.1f}, {high:+.1f}] | {record['medianMillis']:,.0f} ms | "
                f"{str(heap) + ' MiB' if heap else '—'} |")

    split = results["datasets"]["squad2"]["arms"]
    def part(arm, kind, key="exactMatch"):
        return split[arm][kind][key]

    # Which half the difference is on is a fact to read, not a sentence to keep in sync by hand:
    # the screen at n=50 had the 8B behind on the answerable half and the full run does not.
    answerable_gap = part("llama3.1-8b", "answerable") - part("llama1b", "answerable")
    unanswerable_gap = part("llama3.1-8b", "unanswerable") - part("llama1b", "unanswerable")
    hotpot = results["datasets"]["hotpotqa"]["arms"]
    squad = results["datasets"]["squad2"]["arms"]
    multi_hop = {
        arm: (hotpot[arm]["exactMatch"], hotpot[arm].get("answerable", {}).get("abstained", 0))
        for arm in ("llama1b", "llama3.1-8b", "frontier") if arm in hotpot
    }
    out += [
        "",
        "Where the difference is matters more than its size. On SQuAD v2's answerable half the 8B "
        f"arm scores {part('llama3.1-8b', 'answerable'):.1f} against the 1B arm's "
        f"{part('llama1b', 'answerable'):.1f}, a difference of {answerable_gap:+.1f} — and it gets "
        f"there having declined {part('llama3.1-8b', 'answerable', 'abstained'):.0f} questions the "
        f"passage does answer, against the 1B arm's "
        f"{part('llama1b', 'answerable', 'abstained'):.0f}. On the unanswerable half the 1B arm "
        f"scores {part('llama1b', 'unanswerable'):.1f} after declining "
        f"{part('llama1b', 'unanswerable', 'abstained'):.0f} times out of "
        f"{part('llama1b', 'unanswerable', 'n'):.0f}, and the 8B arm scores "
        f"{part('llama3.1-8b', 'unanswerable'):.1f} after declining "
        f"{part('llama3.1-8b', 'unanswerable', 'abstained'):.0f}: a difference of "
        f"{unanswerable_gap:+.1f}, "
        + ("which is almost the whole gap. " if unanswerable_gap > 3 * max(answerable_gap, 0.1)
           else "")
        + "Knowing that the answer is not in the notes is the capability that arrives with size, "
        f"and gpt-5.1 itself declined only "
        f"{part('frontier', 'unanswerable', 'abstained'):.0f} of "
        f"{part('frontier', 'unanswerable', 'n'):.0f} on the same items.",
        "",
        "And then the second dataset says the capability does not generalise, which is the result "
        "this experiment was run to find. HotpotQA gives ten paragraphs and asks a two-hop "
        f"question, and there the 8B arm scores {multi_hop['llama3.1-8b'][0]:.1f} against the 1B "
        f"arm's {multi_hop['llama1b'][0]:.1f} and gpt-5.1's {multi_hop['frontier'][0]:.1f} — "
        + ("**behind the model it replaced**"
           if multi_hop["llama3.1-8b"][0] < multi_hop["llama1b"][0] - 0.05
           else "**level with the model it replaced**"
           if abs(multi_hop["llama3.1-8b"][0] - multi_hop["llama1b"][0]) <= 0.05
           else "ahead of the model it replaced")
        + f" by {abs(multi_hop['llama3.1-8b'][0] - multi_hop['llama1b'][0]):.1f} points, and far "
        "behind the frontier. Worse, and more interesting: HotpotQA has no unanswerable "
        f"questions, and the 8B arm declined **{multi_hop['llama3.1-8b'][1]} of its "
        f"{hotpot['llama3.1-8b']['n']} items anyway**, where the 1B arm declined "
        f"{multi_hop['llama1b'][1]}. The behaviour that won SQuAD v2 — saying so when the passage "
        "does not answer the question — misfires when the passage set is ten paragraphs deep and "
        "the answer needs two of them joined: it refuses questions that do have answers.",
        "",
        "So calibrated abstention is not a capability a model either has or lacks. It is a trade "
        "between two kinds of error, and which way it pays depends on the shape of what retrieval "
        "hands the model. On one short passage it is worth tens of points. On ten paragraphs it "
        "costs answerable items and buys nothing, because nothing in that dataset is unanswerable "
        "to begin with.",
        "",
        "**So `grounding` is a claim no model in this catalog can carry, and the fleet stopped "
        "making it.** The two datasets disagree about which local arm is better -- the 8B by "
        f"{squad['llama3.1-8b']['exactMatch'] - squad['llama1b']['exactMatch']:.1f} points on one "
        f"and the 1B by {multi_hop['llama1b'][0] - multi_hop['llama3.1-8b'][0]:.1f} on the other "
        "-- and neither is close to the frontier model on multi-hop, so the experiment's own "
        "decision rule moves no declaration. What the fleet declares now is "
        "`grounding-single-passage`, on the 8B arm, because that is the shape its retrieval "
        "produces: three one-sentence notes indexed, the top two retrieved, never a two-hop join "
        "over ten paragraphs. The gate maps the narrow name to SQuAD v2 and still holds the broad "
        "name to both datasets, so the narrowing is a smaller claim rather than a softer gate, and "
        "a deployment whose retrieval returns ten paragraphs cannot reuse the declaration.",
        "",
        "What this is not: a claim that an 8B model is cleverer than gpt-5.1. The task is "
        "extraction scored by exact match on short spans, both arms get the identical prompt "
        "asking for the shortest exact phrase and naming the abstention string, and a verbose "
        "answer loses the item however correct it is. Nor is it a claim that a better prompt could "
        "not move the multi-hop number: prompt engineering was out of scope for both arms, and it "
        "is the obvious next experiment rather than a reason to discount this one.",
    ]
    return "\n".join(out)


def chat_arm_region(routed: str, remote: str) -> str:
    """The local-only chat arms: the ordering that decides the declaration, and the ceiling gap."""
    records = measurement_records("local-only-chat")
    results = json.loads((ROOT / "experiments/local-only-chat/RESULTS.json").read_text())
    names = {"coqa": "CoQA dev, free-form conversational QA",
             "quac": "QuAC val, information-seeking dialogue"}
    arms = {"small": "Qwen3 0.6B", "llama1b": "Llama 3.2 1B", "llama3.1-8b": "Llama 3.1 8B"}

    out = ["| arm | public dataset | token F1 | behind the best local arm | gpt-5.1 |"
           " the boundary's cost | declined | median per answer |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for arm, label in arms.items():
        for dataset, dataset_label in names.items():
            record = pick(records, f"chat/{dataset}", arm)
            behind = record["bestLocal"]["behind"]
            out.append(
                f"| {label} | {dataset_label} (n={record['n']}) | **{record['value']:.1f}** | "
                f"{'first' if behind == 0 else f'{behind:.1f} behind'} | "
                f"{record['reference']['value']:.1f} | {record['delta']:+.1f} | "
                f"{record['abstained']} of {record['n']} | "
                f"{record['medianMillis']:,.0f} ms |")

    declaration = results["declaration"]
    best = results.get("bestLocal", {})
    agreed = declaration.get("agreed") or []
    out += [
        "",
        "Two numbers, both published. The ordering among local arms is what the fleet gets to act "
        f"on: {', '.join('`' + a + '`' for a in agreed) if agreed else 'no arm'} "
        f"{'carries' if len(agreed) == 1 else 'carry'} the `chat` declaration on both datasets, "
        f"and the measurement's verdict on the arm this walkthrough shipped is "
        f"**{declaration['call']}**. The distance to gpt-5.1 is what the local-only boundary "
        "costs, and it is in the table rather than in a footnote: a reader deciding whether to "
        "keep that boundary is entitled to its price.",
        "",
        ("The two datasets agree on the ordering: "
         + (("`" + "` and `".join(best["coqa"]) + "` "
             + ("is" if len(best["coqa"]) == 1 else "are tied") + " first on both.")
            if best.get("coqa") == best.get("quac")
            else ("`" + "` and `".join(best.get("coqa", ["?"])) + "` first on CoQA and `"
                  + "` and `".join(best.get("quac", ["?"])) + "` on QuAC, which is a disagreement, "
                  "so the declaration does not move on this evidence."))
         + " What neither dataset can settle is the rest of chat: tone, instruction following, "
           "refusal behaviour and multi-turn task completion are not conversational question "
           "answering, and the declaration this evidence supports is narrower than the word on "
           "the capability."),
    ]
    return "\n".join(out)


def tradeoff_region(routed: str, remote: str) -> str:
    """What routing buys and what it costs, in the direction the current pairs actually measure.

    This paragraph used to say routing "does not reliably buy a smaller latency: on this mix it
    landed on both sides of parity". That was true of a fleet whose grounding and chat arms were a
    1B and a 0.6B. It is not true of the fleet those arms were measured out of, and a sentence that
    describes a previous configuration is the thing this file exists to prevent, so the direction
    is computed rather than written.
    """
    found = pairs()
    if not found:
        raise SystemExit("no archived pairs on the current pin")
    factors, ratios, locals_ = [], [], []
    for stamp, routed_ms, base_ms, local in found:
        rt = (RUNS / f"{stamp}-routed.log").read_text()
        bt = (RUNS / f"{stamp}-all-remote.log").read_text()
        _providers, routed_cost = d.ledger(rt)
        _, _, _, _, base_cost = d.all_remote_total(bt)
        factors.append(base_cost / routed_cost)
        ratios.append(routed_ms / base_ms)
        locals_.append(local)
    spread = max(locals_) / min(locals_)
    slower = min(ratios) > 1
    faster = max(ratios) < 1
    direction = ("costs it" if slower else "buys it" if faster
                 else "lands on both sides of parity for it")
    return (
        f"Routing buys a bill **{min(factors):.2f}× to {max(factors):.2f}× smaller** and a local "
        f"latency you can predict -- the part of the wall clock spent on this machine varies by "
        f"**{spread:.2f}×** across three runs of identical code, where one byte-identical provider "
        "call varies by more than four. What it does to total latency is the other half of the "
        f"trade, and on this fleet it {direction}: "
        f"**{min(ratios):.2f}× to {max(ratios):.2f}×** the no-router arm's wall clock. "
        + ("That is the price of the arms the accuracy section chose. A grounding and chat arm that "
           "answers rather than declines is an 8B model, and an 8B model on six laptop cores is "
           "seconds per answer where a 0.6B was a second -- the same swap that moved the fleet from "
           "16 to 35 points behind gpt-5.1 to within two points of it. A deployment that needs the "
           "old latency can have it back by declaring the smaller arm again, and the gate will then "
           "refuse the capability, which is the honest version of that choice."
           if slower else
           "The cost column is the one that holds still, because the prompts fix the token counts "
           "and nothing about somebody else's queue can move them.")
    )


def declarations_region(routed: str, remote: str) -> str:
    """The parity gate's own table, printed by the gate rather than restated here.

    The gate is the thing that decides whether a declaration stands, so the article shows its
    output instead of a second table that could disagree with it. A run with violations prints
    them in the table, which is the intended behaviour: the article cannot display a clean set of
    declarations unless the gate is actually clean.
    """
    gate = ROOT / "tools/parity_gate.py"
    finished = subprocess.run([sys.executable, str(gate), "--markdown"],
                              capture_output=True, text=True, cwd=ROOT)
    if not finished.stdout.strip():
        raise SystemExit(f"parity_gate.py --markdown printed nothing: {finished.stderr.strip()}")
    table = finished.stdout.strip()
    # The exit code is the violation count, and it belongs in the article as a sentence rather
    # than as an absence.
    if finished.returncode:
        count = finished.returncode
        table += (f"\n\n**{count} of these declarations "
                  + ("is" if count == 1 else "are")
                  + " not supported by a measurement.** The gate fails the build until "
                  + ("it is" if count == 1 else "they are") + ".")
    return table


def threshold_audit_region(routed: str, remote: str) -> str:
    """The threshold experiment's two tables, from its own stage artifacts.

    A threshold the fleet ships is a claim like any other, and until this experiment ran it was
    the one claim in the fleet nobody had measured against an alternative.
    """
    base = ROOT / "experiments/decision-threshold"
    cv = json.loads((base / "stage3-cv.json").read_text())
    cal = json.loads((base / "stage4-calibration.json").read_text())
    sweep = json.loads((base / "stage2-sweep.json").read_text())
    results = json.loads((base / "RESULTS.json").read_text())
    shipped = results["shippedThreshold"]
    labels = {"snips": "SNIPS", "trec": "TREC"}

    out = [
        f"| public dataset | the folds chose | held-out accuracy, tuned | at {shipped} | "
        "escalated share, tuned | at " + str(shipped) + " |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(cv["datasets"]):
        found = cv["datasets"][name]
        out.append(
            f"| {labels[name]} | "
            + ", ".join(f"{x:.2f}" for x in found["selectedThresholds"]) + " | "
            f"{found['heldOutAccuracy']['tunedMean']:.1f} | "
            f"{found['heldOutAccuracy']['shippedMean']:.1f} | "
            f"{found['heldOutEscalatedShare']['tunedMean']:.0f}% | "
            f"{found['heldOutEscalatedShare']['shippedMean']:.0f}% |")

    snips_sweep = sweep["datasets"]["snips"]["shipped"]
    trec_sweep = sweep["datasets"]["trec"]["shipped"]
    out += [
        "",
        "Read as a binary decision — escalate, with the positive class *the local arm was wrong* — "
        f"the gate at {shipped} has precision **{snips_sweep['precision']:.3f}** and recall "
        f"**{snips_sweep['recall']:.3f}** on SNIPS, and **{trec_sweep['precision']:.3f}** and "
        f"**{trec_sweep['recall']:.3f}** on TREC. It catches nearly every mistake and pays by "
        "escalating questions the arm had right. The requirement the post starts from — at least "
        "0.80 of each — is **met by no threshold on either dataset, on any of the five training "
        "splits**, so by that criterion this decision model would be ruled out as a judge. It is "
        "still the right arm for this fleet, because the gate is not the product: the combined "
        "arm's accuracy is, and it is bought by over-escalating.",
        "",
        "Cross-validation picked a lower threshold on every fold and it measured **worse**: fewer "
        "provider calls, less accuracy, on both datasets. Under the rule written before the "
        f"analysis ran, that is a null and the shipped {shipped} stays — kept because a cheaper "
        "gate was measured and lost, which is a different thing from kept because nobody looked.",
        "",
        "| public dataset | mean confidence | observed accuracy | ECE | Brier, as reported | "
        "Brier, Platt-scaled | 95% CI of the change |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in sorted(cal["datasets"]):
        found = cal["datasets"][name]
        brier = found["brier"]
        out.append(
            f"| {labels[name]} | {found['meanConfidence']:.3f} | "
            f"{found['observedAccuracy']:.3f} | {found['expectedCalibrationError']:.3f} | "
            f"{brier['reported']:.4f} | {brier['plattScaled']:.4f} | "
            f"[{brier['deltaCi95'][0]:+.4f}, {brier['deltaCi95'][1]:+.4f}] |")

    means = {n: cal["datasets"][n]["shippedThresholdCalibratedMean"] for n in cal["datasets"]}
    out += [
        "",
        "The confidence the gate reads is **not calibrated**, and it errs the useful way round: "
        f"the arm is right {cal['datasets']['snips']['observedAccuracy'] * 100:.0f}% of the time "
        f"on SNIPS while reporting {cal['datasets']['snips']['meanConfidence']:.3f}, and "
        f"{cal['datasets']['trec']['observedAccuracy'] * 100:.0f}% on TREC while reporting "
        f"{cal['datasets']['trec']['meanConfidence']:.3f}. Platt scaling fitted on the training "
        "folds improves the held-out Brier score on both by point estimate, conclusively on TREC "
        "and inconclusively on SNIPS, and it is adopted as a reporting change only: a monotone "
        "recalibration cannot move which questions this gate escalates, only the number printed "
        "beside an answer.",
        "",
        "Which leaves the translation, and it is the part worth carrying away. Once the score is "
        f"calibrated, the shipped threshold of {shipped} means *escalate unless this answer is "
        f"about {means['snips'] * 100:.0f}% likely to be right* on SNIPS and "
        f"{means['trec'] * 100:.0f}% on TREC — nearly the same requirement on both, even though "
        "one escalates a third of its questions and the other three quarters. The gate's meaning "
        "is stable across the two datasets; what differs is how hard the questions are. A "
        "threshold that reads as \"escalate when less than 60% sure\" is doing something "
        "considerably stricter than it sounds.",
    ]
    return "\n".join(out)


def rulers_region(routed: str, remote: str) -> str:
    """The two token rulers, read from the ledger lines the demo prints.

    This sentence used to quote a hand-typed pair of counts for "the escalated prompts", which
    was true of a run three pins ago and survived two re-measurements without anybody noticing,
    because nothing could check it. The demo computes both rulers; this reads them.
    """
    local = re.search(
        r"local ruler \(([^)]+)\): (\d+) of (\d+) input tokens were routed off this machine"
        r" \(([\d.]+)%\)", routed)
    provider = re.search(
        r"provider ruler \(([^)]+) reported\): (\d+) input \+ (\d+) completion tokens billed",
        routed)
    if not (local and provider):
        raise SystemExit("the routed log does not print both token rulers")
    tokenizer, left, offered, share = local.groups()
    billed = int(provider.group(2))
    gap = int(left) - billed
    return (
        f"Token counts are each provider's own report or the {tokenizer}'s, kept apart because "
        f"they disagree about the same bytes. On the local ruler **{thousands(int(left))} of "
        f"{thousands(int(offered))}** input tokens left this machine ({share}%); the providers "
        f"billed **{thousands(billed)}** for exactly that text, a gap of "
        f"**{thousands(abs(gap))} tokens** ({abs(gap) / int(left) * 100:.1f}%). The direction is "
        + ("the safe one: the local ruler counts more than the providers bill, so a budget planned "
           "on it overestimates rather than under"
           if gap > 0 else
           "the unsafe one: the local ruler counts fewer tokens than the providers bill, so a "
           "budget planned on it underestimates the invoice")
        + ". Shares are quoted on the local ruler, where every prompt is measured identically, "
        "and bills on the provider's, where they are charged.")


def saving_spread_region(routed: str, remote: str) -> str:
    """How far the headline saving moved across the archived pairs on this pin.

    The list of percentages here was hand-maintained and had accumulated figures from pairs
    measured on earlier pins, which is an average over two different fleets.
    """
    found = pairs()
    percents, factors = [], []
    for stamp, *_rest in found:
        rt = (RUNS / f"{stamp}-routed.log").read_text()
        bt = (RUNS / f"{stamp}-all-remote.log").read_text()
        _providers, routed_cost = d.ledger(rt)
        *_head, base_cost = d.all_remote_total(bt)
        percents.append(float((base_cost - routed_cost) / base_cost * 100))
        factors.append(float(base_cost / routed_cost))
    pairs_word = WORDS.get(len(found), str(len(found)))
    return (
        "One thing about the comparison itself. The headline percentage moves between runs, "
        "because gpt-5.1 bills its reasoning as completion tokens and does not spend the same "
        f"amount twice. Across the {pairs_word} archived pairs on this pin it came out at "
        f"**{min(percents):.1f}% to {max(percents):.1f}%** — a factor of "
        f"**{min(factors):.2f}× to {max(factors):.2f}×**. Read it as roughly "
        f"**{statistics.median(percents):.0f}%, a factor of three**, and expect it to move with "
        "how much reasoning the provider decides to bill.")


def remotes_region(routed: str, remote: str) -> str:
    """The remote line-up, from fleet.java and from the size of the prompt only they can take."""
    declared = provider_declarations()
    biggest = max(tokens for _text, _model, tokens, _ms in d.routed_prompt_rows(routed))
    fit = [d_ for d_ in declared if d_["window"] >= biggest]
    reasoning = [d_["id"] for d_ in declared if "reasoning" in d_["capabilities"]]
    too_small = [d_ for d_ in declared if d_ not in fit]
    windows = ", ".join(f"{thousands(d_['window'])} for `{d_['id']}`" for d_ in declared)
    return (
        f"The fleet holds {WORDS[len(declared)]} remote providers alongside its local arms, at two "
        f"vendors, through two endpoints, two credentials and two response shapes. Only "
        f"{', '.join(f'`{i}`' for i in reasoning)} declares `reasoning`, which is why the "
        "synthesis prompt has exactly one place it can go. The rest of the line-up is settled by "
        f"the windows they declare — {windows} — against a prompt of {thousands(biggest)} tokens: "
        f"{WORDS[len(fit)]} of them can take it, and "
        + ", ".join(f"`{d_['id']}` cannot, at {thousands(d_['window'])}" for d_ in too_small)
        + ". Which of the "
        f"{WORDS[len(fit)]} serves it is then a policy question rather than a vendor decision "
        "written into the code, and each client normalises its own provider's usage into one "
        "`RoutingUsage`, which is the only thing the ledger needs.")


def price_spread_region(routed: str, remote: str) -> str:
    """The spread between the remotes' declared rates, computed rather than characterised.

    "Two orders of magnitude on output" stood here over a line-up whose output rates span 20x.
    A ratio is cheap to divide and expensive to assert.
    """
    declared = provider_declarations()
    cheapest_in = min(declared, key=lambda d_: d_["in"])
    dearest_in = max(declared, key=lambda d_: d_["in"])
    cheapest_out = min(declared, key=lambda d_: d_["out"])
    dearest_out = max(declared, key=lambda d_: d_["out"])
    return (
        f"{WORDS[len(declared)].capitalize()} of them, at two vendors, declared at rates that span "
        f"**{dearest_in['in'] / cheapest_in['in']:.0f}x on input** "
        f"(${dearest_in['in']:.2f} for `{dearest_in['id']}` against ${cheapest_in['in']:.2f} for "
        f"`{cheapest_in['id']}`) and **{dearest_out['out'] / cheapest_out['out']:.0f}x on output** "
        f"(${dearest_out['out']:.2f} against ${cheapest_out['out']:.2f}), per million tokens.")


REGIONS = {
    "threshold-audit": threshold_audit_region,
    "price-spread": price_spread_region,
    "remotes": remotes_region,
    "rulers": rulers_region,
    "saving-spread": saving_spread_region,
    "accuracy": accuracy_region,
    "declarations": declarations_region,
    "tradeoff": tradeoff_region,
    "escalation": escalation_region,
    "conclusion": conclusion_region,
    "grounding-arm": grounding_arm_region,
    "chat-arm": chat_arm_region,
    "baseline": baseline_region,
    "summary": summary_region,
    "grouping": grouping_region,
    "provider-latency": provider_latency_region,
    "cost": cost_region,
    "per-prompt": per_prompt_region,
    "variance": lambda routed, remote: variance_region(),
}


# The regions that describe a run pair, as opposed to the ones that describe a measurement. The
# quality tables do not need a run at all, and coupling them to one meant that re-pinning the demo
# -- which invalidates the archived pairs until it is re-measured -- also blocked regenerating a
# table about an experiment that had nothing to do with the pins.
NEEDS_RUN_PAIR = frozenset(
    {"baseline", "summary", "grouping", "provider-latency", "cost", "per-prompt", "variance",
     "conclusion", "tradeoff", "rulers", "saving-spread", "remotes", "price-spread"})


def main() -> int:
    stamp, routed, remote = latest_pair()
    # `latest_pair` hands back the newest archived pair whatever it was measured on; `pairs`
    # filters to the pins the demo resolves today. Re-pinning the demo therefore leaves archived
    # logs that must not be read, and the regions that read them have to be refused by name rather
    # than by whichever one happens to run first.
    pair_failure = None
    if not pairs():
        pair_failure = (f"the archived pairs were measured on other pins than "
                        f"modeljars:{current_pin()}, which the demo resolves today")
    # The run record quotes the same generated blocks as the article, so the two cannot disagree
    # about a number that was measured once.
    targets = [ARTICLE, ROOT / "evidence/fleet-routing/RESULTS.md"]
    written = {name: 0 for name in REGIONS}
    blocked: set[str] = set()

    for path in targets:
        text = path.read_text()
        before = text
        for name, build in REGIONS.items():
            pattern = re.compile(
                r"<!-- figures:" + re.escape(name) + r" -->(?:\n.*?)?<!-- end:figures:"
                + re.escape(name) + r" -->", re.S)
            matches = list(pattern.finditer(text))
            if len(matches) > 1:
                raise SystemExit(f"{path.name}: figures:{name} appears {len(matches)} times")
            if not matches:
                continue
            if pair_failure and name in NEEDS_RUN_PAIR:
                blocked.add(name)
                continue
            body = build(routed, remote)
            text = (text[: matches[0].start()]
                    + f"<!-- figures:{name} -->\n{body}\n<!-- end:figures:{name} -->"
                    + text[matches[0].end():])
            written[name] += 1
        if path == ARTICLE and not pair_failure:
            verify_prose(text, routed)
        if text != before:
            path.write_text(text)

    missing = [name for name, count in written.items()
               if count == 0 and name not in blocked]
    if missing:
        raise SystemExit(f"no file carries the region{'s' if len(missing) > 1 else ''} {missing}")
    print(f"regenerated {sum(written.values())} figure regions from run {stamp}, "
          "hand-written figures checked")
    if blocked:
        # Written what could be written, then failed. A tool that silently left a table describing
        # a previous run is the drift this file exists to stop; a tool that refuses to regenerate
        # anything because one input is stale is just as unhelpful.
        raise SystemExit(
            f"{len(blocked)} region(s) describe a run pair and could not be regenerated: "
            f"{sorted(blocked)}\n{pair_failure}\nRe-measure the fleet on the current pins "
            "(tools/measure_on_isolated_host.sh) and run this again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
