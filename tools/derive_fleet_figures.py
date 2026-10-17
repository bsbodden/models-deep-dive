#!/usr/bin/env python3
"""Derive the comparison figures in the article from the two committed fleet.java logs.

Reads evidence/fleet-routing/routed.log and evidence/fleet-routing/all-remote.log --
the raw stdout of `jbang fleet.java` and `jbang fleet.java all-remote` -- and prints
every figure the article states about the two arms. Nothing here is typed by hand:
if a figure is not printed by this script, it does not go in the article.
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTED = ROOT / "evidence/fleet-routing/routed.log"
ALL_REMOTE = ROOT / "evidence/fleet-routing/all-remote.log"


def section(text: str, header: str) -> str:
    """The lines after a `== header ==` banner, up to the next banner or EOF."""
    start = text.index(f"== {header} ==") + len(f"== {header} ==")
    rest = text[start:]
    end = rest.find("\n== ")
    return rest if end < 0 else rest[:end]


def routed_prompt_rows(text: str) -> list[tuple[str, str, int, int]]:
    """(prompt, selected, tokens, ms) for each prompt, from the routing table.

    Column positions are read from the header rather than hard-coded, so widening a column in
    fleet.java does not silently reduce this to zero rows and a wrong comparison.
    """
    body = text[text.index("PROMPT ") : text.index("== timing")]
    lines = body.splitlines()
    header = lines[0]
    selected_at = header.index("SELECTED")
    rows = []
    for line in lines[1:]:
        if len(line) <= selected_at or not line[:1].strip():
            continue
        m = re.match(r"^(\S+)\s+(\d+)\s+(\d+)\s*$", line[selected_at:])
        if m:
            rows.append(
                (line[: header.index("CLASSIFIED")].strip(), m.group(1), int(m.group(2)), int(m.group(3)))
            )
    return rows


def timing_rows(text: str) -> dict[str, tuple[int, int, int]]:
    """model -> (calls, total ms, mean ms) from the warm timing table."""
    out = {}
    for line in section(text, "timing, warm").splitlines():
        m = re.match(r"^(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[\d.]+%\s*$", line)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return out


def ledger(text: str) -> tuple[dict[str, tuple[int, int, Decimal]], Decimal]:
    """provider -> (input, completion, cost), plus the routed total."""
    providers, total = {}, None
    for line in section(text, "ledger").splitlines():
        m = re.match(r"^(\S+)\s+(\d+)\s+(\d+)\s+\$([\d.]+)\s*$", line)
        if not m:
            continue
        if m.group(1) == "total":
            total = Decimal(m.group(4))
        else:
            providers[m.group(1)] = (int(m.group(2)), int(m.group(3)), Decimal(m.group(4)))
    if total is None:
        raise SystemExit("routed.log: no ledger total")
    return providers, total


def all_remote_rows(text: str) -> list[tuple[str, int, int, int]]:
    """(prompt, input, completion, ms) per prompt from the no-router table."""
    body = text[text.index("PROMPT ") : text.index("== every prompt")]
    rows = []
    for line in body.splitlines()[1:]:
        m = re.match(r"^(\S.*?)\s\s+(\d+)\s+(\d+)\s+(\d+)\s*$", line)
        if m:
            rows.append(
                (m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            )
    return rows


def all_remote_total(text: str) -> tuple[int, int, Decimal, Decimal, Decimal]:
    body = section(text, "every prompt through gpt-5.1")
    tokens = re.search(r"provider-reported: (\d+) input \+ (\d+) completion", body)
    priced = re.search(r"at the declared \$([\d.]+)/M in, \$([\d.]+)/M out: \$([\d.]+)", body)
    if not tokens or not priced:
        raise SystemExit("all-remote.log: counterfactual block not parseable")
    return (
        int(tokens.group(1)),
        int(tokens.group(2)),
        Decimal(priced.group(1)),
        Decimal(priced.group(2)),
        Decimal(priced.group(3)),
    )


def declared_prices() -> dict[str, Decimal]:
    """The price constants the demo declares, read from its source."""
    src = (ROOT / "code/fleet.java").read_text()
    return {
        m.group(1): Decimal(m.group(2))
        for m in re.finditer(r"static final double (\w+_(?:IN|OUT)) = ([\d.]+);", src)
    }


def main() -> int:
    routed = ROUTED.read_text()
    remote = ALL_REMOTE.read_text()

    rows = routed_prompt_rows(routed)
    providers, routed_cost = ledger(routed)
    far = all_remote_rows(remote)
    ar_in, ar_out, in_price, out_price, ar_cost = all_remote_total(remote)

    if len(rows) != len(far):
        raise SystemExit(f"arms disagree on prompt count: {len(rows)} vs {len(far)}")
    if sum(r[1] for r in far) != ar_in or sum(r[2] for r in far) != ar_out:
        raise SystemExit("all-remote per-prompt rows do not sum to the reported totals")

    remote_models = set(providers)
    local_idx = [i for i, r in enumerate(rows) if r[1] not in remote_models]

    saved = ar_cost - routed_cost
    pct = saved / ar_cost * 100
    factor = ar_cost / routed_cost

    local_out = sum(far[i][2] for i in local_idx)
    local_in = sum(far[i][1] for i in local_idx)
    local_cost = (Decimal(local_in) * in_price + Decimal(local_out) * out_price) / Decimal(1_000_000)
    local_share = local_cost / ar_cost * 100

    print(f"prompts: {len(rows)}, answered locally: {len(local_idx)}, escalated: {len(rows) - len(local_idx)}")
    print(f"all-remote: {ar_in} input + {ar_out} completion = ${ar_cost}")
    print(f"as routed:  {sum(p[0] for p in providers.values())} input + "
          f"{sum(p[1] for p in providers.values())} completion = ${routed_cost}")
    print(f"saved: ${saved} -- {pct:.1f}% less, a factor of {factor:.2f}")
    print(f"the {len(local_idx)} locally answered prompts would have billed {local_out} completion "
          f"tokens on gpt-5.1, or ${local_cost.quantize(ar_cost)} -- {local_share:.1f}% of the all-remote bill")

    declared = declared_prices()
    for name, (pin, pout, cost) in providers.items():
        print(f"  {name}: {pin} in + {pout} completion = ${cost}")
    print("declared list prices per million tokens, from code/fleet.java:")
    for const, value in declared.items():
        print(f"  {const} = {value}")
    spread = declared["PREMIUM_OUT"] / declared["HAIKU_OUT"]
    print(f"on completion, PREMIUM_OUT is {spread:.0f} times HAIKU_OUT "
          f"(${declared['PREMIUM_OUT']} against ${declared['HAIKU_OUT']} per million)")

    timing = timing_rows(routed)
    if "gpt-5.1" in timing and "claude-haiku-5-5" in timing:
        slow, fast = timing["gpt-5.1"][2], timing["claude-haiku-5-5"][2]
        print(f"gpt-5.1 mean {slow} ms vs claude-haiku-5-5 mean {fast} ms: "
              f"Haiku {Decimal(slow) / Decimal(fast):.1f} times faster")

    wall = re.search(r"conversation wall clock: (\d+) ms, of which (\d+) ms \(([\d.]+)%\)", routed)
    load = re.search(r"one-off load of the four local models: (\d+) ms", routed)
    base_wall = re.search(r"conversation wall clock: (\d+) ms", remote)
    if wall and load:
        print(f"routed wall clock {wall.group(1)} ms, {wall.group(2)} ms ({wall.group(3)}%) in model "
              f"calls; one-off load {load.group(1)} ms")
    if base_wall and wall:
        b, r = int(base_wall.group(1)), int(wall.group(1))
        print(f"no-router wall clock {b} ms; routed is {r - b:+d} ms ({(r - b) / b * 100:+.1f}%)")

    print("per-prompt wall clock, no-router vs routed:")
    for (text, _, _, base_ms), routed_row in zip(far, rows):
        print(f"  {text[:40]:<42} {base_ms:>6} ms -> {routed_row[3]:>6} ms "
              f"({routed_row[1][:28]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
