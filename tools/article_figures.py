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

import re
import statistics
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
        f"{len(local_idx)} of the {len(rows)} prompts never left the machine. The "
        f"{len(escalated)} that escalated did not go to the same provider: {where} — and that "
        "second choice is most of the story.",
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


REGIONS = {
    "baseline": baseline_region,
    "grouping": grouping_region,
    "provider-latency": provider_latency_region,
    "cost": cost_region,
    "per-prompt": per_prompt_region,
    "variance": lambda routed, remote: variance_region(),
}


def main() -> int:
    stamp, routed, remote = latest_pair()
    # The run record quotes the same generated blocks as the article, so the two cannot disagree
    # about a number that was measured once.
    targets = [ARTICLE, ROOT / "evidence/fleet-routing/RESULTS.md"]
    written = {name: 0 for name in REGIONS}

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
            body = build(routed, remote)
            text = (text[: matches[0].start()]
                    + f"<!-- figures:{name} -->\n{body}\n<!-- end:figures:{name} -->"
                    + text[matches[0].end():])
            written[name] += 1
        if path == ARTICLE:
            verify_prose(text, routed)
        if text != before:
            path.write_text(text)

    missing = [name for name, count in written.items() if count == 0]
    if missing:
        raise SystemExit(f"no file carries the region{'s' if len(missing) > 1 else ''} {missing}")
    print(f"regenerated {sum(written.values())} figure regions from run {stamp}, "
          "hand-written figures checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
