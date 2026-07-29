#!/usr/bin/env python3
"""
test_rules.py — asserts rules.py's rule_a/rule_b/rule_c match the exact
boundary cases src/origin.rs's own unit tests cover (rule_a_*, rule_b_*,
rule_c_* in that file's `#[cfg(test)] mod tests`). Run directly: `python3
test_rules.py`. No pytest dependency — this only needs to run once per
harness change, not on every build.
"""
import sys

from rules import rule_a, rule_b, rule_c


def only(cls, n):
    return {cls: n}


def check(label, got, want):
    status = "ok" if got == want else "FAIL"
    print(f"  [{status}] {label}: got={got} want={want}")
    return got == want


def main():
    ok = True

    # RuleA — mirrors rule_a_* in src/origin.rs
    ok &= check("rule_a zero locations", rule_a({}, 2), "NONE")
    ok &= check("rule_a any non-user is dep", rule_a({"user": 5, "rustc": 1}, 2), "DEP")
    ok &= check("rule_a all-user at threshold", rule_a(only("user", 2), 2), "AUTHOR")
    ok &= check("rule_a all-user below threshold", rule_a(only("user", 1), 2), "AMBIGUOUS")
    ok &= check("rule_a sweep n=4 below", rule_a(only("user", 3), 4), "AMBIGUOUS")
    ok &= check("rule_a sweep n=4 at", rule_a(only("user", 4), 4), "AUTHOR")
    ok &= check("rule_a n=1 no ambiguous band", rule_a(only("user", 1), 1), "AUTHOR")

    # RuleB — mirrors rule_b_* in src/origin.rs
    ok &= check("rule_b zero locations", rule_b({}, 2), "NONE")
    ok &= check("rule_b registry hard dep", rule_b({"user": 10, "registry": 1}, 2), "DEP")
    ok &= check("rule_b git hard dep", rule_b({"user": 10, "git": 1}, 2), "DEP")
    ok &= check("rule_b rustc does not block author", rule_b({"user": 2, "rustc": 5}, 2), "AUTHOR")
    ok &= check("rule_b user below threshold ambiguous", rule_b({"user": 1, "rustc": 3}, 2), "AMBIGUOUS")
    ok &= check("rule_b user zero only rustc is dep", rule_b(only("rustc", 4), 2), "DEP")

    # RuleC — mirrors rule_c_* in src/origin.rs
    ok &= check("rule_c zero total", rule_c({}, 0.5), "NONE")
    ok &= check("rule_c above threshold", rule_c({"user": 3, "rustc": 1}, 0.5), "AUTHOR")
    ok &= check("rule_c below threshold", rule_c({"user": 1, "rustc": 3}, 0.5), "DEP")
    ok &= check("rule_c exactly at threshold", rule_c({"user": 2, "rustc": 2}, 0.5), "AUTHOR")

    if ok:
        print("all rules.py boundary cases match src/origin.rs's unit tests")
        return 0
    print("MISMATCH: rules.py has drifted from src/origin.rs", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
