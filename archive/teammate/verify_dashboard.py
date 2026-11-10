"""Independent exact arithmetic check for the dashboard's C40 rail scenario."""

from bisect import bisect_right
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import json
import random
import subprocess


ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "vanino-model.js"


def rail_charge(days):
    # Tariff table 2 for C40, with the November 2026 coefficients.
    hours = days * 24
    charged = (hours + F(3, 4)) // 1
    before, after = min(charged, 72), max(charged - 72, 0)
    amount = (before * F("11.33") + after * F("15.79")) * F("2.663") * F("1.01")
    return (amount + F(1, 2)) // 1


def compare(state):
    platforms, wait, elapsed = (F(str(state[key])) for key in ("n", "wait", "elapsed"))
    daily, sea, move, storage = (F(str(state[key])) for key in ("extra", "sea", "earlyMove", "storageDays"))

    def contract_charge(days):
        return (-(-days // 1) if state["round"] else days) * daily

    rail_paid = rail_charge(elapsed)
    contract_paid = contract_charge(elapsed)
    charge_stay = state.get("chargeRzdStay", 1)
    charge_divert = state.get("chargeRzdDivert", 1)

    def waiting_cost(days):
        return platforms * (
            charge_stay * (rail_charge(elapsed + days) - rail_paid)
            + contract_charge(elapsed + days) - contract_paid
        )

    release_times = [elapsed + F(1, 2) + F(i, 40) for i in range(int(platforms))]
    rail_residual = charge_divert * sum(rail_charge(time) - rail_paid for time in release_times)
    contract_residual = sum(contract_charge(time + F(1, 2)) - contract_paid for time in release_times)
    alt_rate = F(str(state.get("altRate", 17500)))
    storage_rate = F(str(state.get("storageRate", 500)))
    share = F(str(state.get("share", 50)))
    outside_cost = platforms * (alt_rate + storage_rate * storage + move) + 20000 + sea
    avoided_port_cost = platforms * F("29467.84") * share / 100
    transfer = outside_cost - avoided_port_cost + rail_residual + contract_residual
    # Compare on the same hourly grid as the UI, without invoking the dashboard model.
    hour = bisect_right(range(180 * 24 + 1), transfer, key=lambda h: waiting_cost(F(h, 24)))
    threshold = None if hour > 180 * 24 else F(hour, 24)
    return {
        "stay": waiting_cost(wait),
        "divert": transfer,
        "benefit": waiting_cost(wait) - transfer,
        "residualRzd": rail_residual,
        "residualContract": contract_residual,
        "threshold": threshold,
    }, waiting_cost


def check():
    rng = random.Random(20261110)
    defaults = dict(n=20, wait=4, elapsed=0, extra=0, sea=0, earlyMove=5000, storageDays=2, round=0)
    named = [
        ("4 days, RZD only", {}),
        ("14 days, RZD only", {"wait": 14}),
        ("4 days, proportional contract", {"extra": 4000}),
        ("4 days, no RZD fee in stay branch", {"chargeRzdStay": 0}),
        ("4 days, no RZD fee in divert branch", {"chargeRzdDivert": 0}),
        ("4 days, local starting price, cost overrides", {"altRate": 14000, "storageRate": 0, "share": 65}),
        ("4 days, started-day contract", {"extra": 4000, "round": 1}),
        ("4 days, proportional contract, +500k sea", {"extra": 4000, "sea": 500000}),
        ("zero result", {"wait": 14, "sea": 61888.4}),
    ]
    states = [{**defaults, **overrides} for _, overrides in named]
    for n, wait, elapsed, rounding in product(
        [1, 20, 60], [0, 0.25, 2.75, 3, 3.25, 14, 180], [0, 2.75, 3, 179.75], [0, 1]
    ):
        states.append({**defaults, "n": n, "wait": wait, "elapsed": elapsed, "round": rounding, "extra": 4000})
    for _ in range(600):
        states.append(dict(
            n=rng.randint(1, 60), wait=rng.randint(0, 720) / 4, elapsed=rng.randint(0, 720) / 4,
            extra=rng.randint(0, 10_000_000) / 100, sea=rng.randint(0, 100_000_000),
            earlyMove=rng.randint(0, 1000000), storageDays=rng.randint(0, 720) / 4, round=rng.randrange(2),
            altRate=rng.randint(0, 10_000_000) / 100, storageRate=rng.randint(0, 10_000_000) / 100,
            share=rng.randint(0, 10000) / 100, chargeRzdStay=rng.randrange(2), chargeRzdDivert=rng.randrange(2),
        ))
    node = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const model = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8') + '\nVaninoModel');
const states = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(states.map(inputs => {
  const s = { ...model.defaults, ...inputs };
  return { ...model.calc(s), threshold: model.threshold(s), graphCost: model.waitingCost(s, s.wait) };
})));
"""
    raw = subprocess.check_output(["node", "-e", node, str(MODEL)], input=json.dumps(states).encode("ascii"))
    results = json.loads(raw)
    assert len(results) == len(states)
    worst_difference = 0
    for index, (state, actual) in enumerate(zip(states, results)):
        expected, waiting_cost = compare(state)
        for field, value in {**expected, "graphCost": expected["stay"]}.items():
            if value is None:
                assert actual[field] is None, (index, field, actual[field])
                continue
            error = abs(actual[field] - float(value))
            worst_difference = max(worst_difference, error)
            assert error < 0.00001, (index, field, actual[field], value)
        if index < len(named):
            minute = bisect_right(range(180 * 1440 + 1), expected["divert"], key=lambda m: waiting_cost(F(m, 1440)))
            print(named[index][0], {k: float(v) if v is not None else None for k, v in expected.items()},
                  "first profitable minute:", minute if minute <= 180 * 1440 else None)
    print(f"{len(states)} cases, {len(states) * 7} comparisons, max numerical difference {worst_difference:g}")


if __name__ == "__main__":
    check()
