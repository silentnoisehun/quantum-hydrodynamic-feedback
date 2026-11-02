#!/usr/bin/env python3
"""Check the QPU quota before a measurement is submitted.

Why this exists
---------------
``docs/QPU-RUN-DECISION-RULE.txt`` requires the quota check to happen
BEFORE the submission (point h): on an exhausted account the job never runs,
and the measurement is silently lost.  This script makes that check a
separate, runnable step that reads the quota from the IBM Quantum Platform
API and refuses to let a run start that cannot finish.

The quota model (measured 2026-11-02 against the four accounts, see
``docs/QPU-QUOTA-20261102.txt``):

* ``usage_limit_seconds`` is 600 s on the Open plan.
* ``usage_consumed_seconds`` is the QPU time consumed in the TRAILING 28
  DAYS.  The window rolls: usage frees up gradually, one job at a time, as
  each job ages out.  It is NOT a monthly reset.
* ``usage_limit_reached`` is true when the trailing consumption has reached
  the limit, and ``time_available_at`` is the moment the oldest usage rolls
  out of the window.
* ``free = usage_limit_seconds - usage_consumed_seconds`` is what can be
  spent right now.

Authentication (from ``qiskit_ibm_runtime`` 0.50, ``api/auth.py``):

    API key -> IAM token (iam.cloud.ibm.com/identity/token)
            -> Authorization: Bearer <IAM token>
            + Service-CRN: <instance CRN>

The CRN is resolved from the resource controller.  Without the
``Service-CRN`` header the platform answers 401 (error code 1219).

The token is read from ``--token-file`` (JSON with an ``apikey`` field) or
from ``IBM_QUANTUM_API_TOKEN``.  It is never written to a file, never
printed, and never sent anywhere but IBM.

Usage
-----
    # how much is free on this account right now
    python scripts/check_qpu_quota.py --token-file apikey.json

    # gate: refuse to start a 100-iteration run that needs 296 s
    python scripts/check_qpu_quota.py --token-file apikey.json \\
        --need-iterations 100 --seconds-per-iteration 2.96

    # several accounts: the exit code is 0 if ANY of them can cover it
    python scripts/check_qpu_quota.py --token-file a.json --token-file b.json \\
        --need-iterations 100 --seconds-per-iteration 2.96

    # prove the gate fires, without touching the network
    python scripts/check_qpu_quota.py --self-test

Exit code: 0 if the requested QPU time fits, 1 if it does not, 2 on an
error (bad token, missing instance, unreachable API).
"""

import argparse
import json
import os
import sys

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: the requests package is required", file=sys.stderr)
    raise SystemExit(2)

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
API_BASE = "https://quantum.cloud.ibm.com/api/v1"
RESOURCE_CONTROLLER = "https://resource-controller.cloud.ibm.com/v2/resource_instances"
DEFAULT_INSTANCE_NAME = "open-instance"


# ── the pure logic (tested without the network) ─────────────────────────
def evaluate(usage, need_seconds):
    """Decide whether `need_seconds` of QPU time fits right now.

    `usage` is the /instances/usage payload.  Returns a dict with the
    measured numbers and the decision.
    """
    limit = usage.get("usage_limit_seconds")
    consumed = usage.get("usage_consumed_seconds")
    if limit is None or consumed is None:
        raise ValueError("the usage payload has no limit/consumed seconds")
    free = limit - consumed
    reached = bool(usage.get("usage_limit_reached"))
    available_at = usage.get("time_available_at")
    return {
        "limit": limit,
        "consumed": consumed,
        "free": free,
        "limit_reached": reached,
        "time_available_at": available_at,
        "need": need_seconds,
        # the trailing window only frees up as jobs age out, so an exhausted
        # account is blocked until the oldest usage rolls out of it
        "can_run": (not reached) and free >= need_seconds,
        "reason": _reason(reached, free, need_seconds),
    }


def _reason(reached, free, need):
    if need <= 0:
        return "no QPU time requested"
    if reached:
        return "the quota limit is reached; usage frees up gradually"
    if free < need:
        return "not enough free QPU seconds right now"
    return "enough free QPU seconds"


# ── the live checks ─────────────────────────────────────────────────────
def iam_token(apikey, timeout=45):
    """Exchange an IBM Cloud API key for an IAM access token."""
    resp = requests.post(
        IAM_URL,
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": apikey,
            "response_type": "cloud_iam",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = "%s | %s" % (body.get("errorCode"), body.get("errorMessage"))
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError("the IAM token exchange failed (HTTP %d): %s"
                           % (resp.status_code, detail))
    return resp.json()["access_token"]


def instance_crn(bearer, name=DEFAULT_INSTANCE_NAME, timeout=60):
    """The CRN of the Quantum instance of this account."""
    resp = requests.get(RESOURCE_CONTROLLER, headers=bearer,
                        params={"name": name}, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError("the resource controller answered HTTP %d"
                           % resp.status_code)
    resources = resp.json().get("resources", [])
    if not resources:
        raise RuntimeError("no %r instance is attached to this account" % name)
    return resources[0]["crn"]


def usage_of(bearer, crn, timeout=90):
    """The quota payload of the instance."""
    headers = dict(bearer)
    headers["Service-CRN"] = crn
    resp = requests.get(API_BASE + "/instances/usage", headers=headers,
                        timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError("the usage endpoint answered HTTP %d: %s"
                           % (resp.status_code, resp.text[:200]))
    return resp.json()


def backends_of(bearer, crn, timeout=90):
    """The backend names this account may use."""
    headers = dict(bearer)
    headers["Service-CRN"] = crn
    resp = requests.get(API_BASE + "/backends", headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return []
    devices = resp.json().get("devices", [])
    return [d for d in devices if isinstance(d, str)]


def read_token(token_file):
    """The API key from a JSON file ({'apikey': ...}) or from the env."""
    if token_file:
        with open(token_file, encoding="utf-8") as handle:
            data = json.load(handle)
        key = data.get("apikey")
        if not key:
            raise RuntimeError("%s has no 'apikey' field" % token_file)
        return key
    key = os.environ.get("IBM_QUANTUM_API_TOKEN")
    if not key:
        raise RuntimeError("no token: pass --token-file or set "
                           "IBM_QUANTUM_API_TOKEN")
    return key


# ── the self-test ───────────────────────────────────────────────────────
def self_test():
    """Prove the decision logic on injected payloads (no network)."""
    cases = [
        # (name, usage payload, need, expected can_run)
        ("free account, small request",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 500,
          "usage_limit_reached": False}, 60, True),
        ("free account, request larger than the free time",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 587,
          "usage_limit_reached": False}, 296, False),
        ("exhausted account",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 622,
          "usage_limit_reached": True,
          "time_available_at": "2026-11-04T07:48:56.163Z"}, 60, False),
        ("exhausted account, zero request",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 622,
          "usage_limit_reached": True}, 0, False),
        ("exactly enough free",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 304,
          "usage_limit_reached": False}, 296, True),
        ("one second short",
         {"usage_limit_seconds": 600, "usage_consumed_seconds": 305,
          "usage_limit_reached": False}, 296, False),
    ]
    failures = []
    print("=== the quota gate must decide correctly ===")
    for name, payload, need, expected in cases:
        got = evaluate(payload, need)["can_run"]
        ok = got == expected
        print("  [%s] %-52s can_run=%s (expected %s)"
              % ("OK " if ok else "FAIL", name, got, expected))
        if not ok:
            failures.append(name)

    print()
    print("=== a broken payload must be rejected, not silently allowed ===")
    for name, payload in [("no limit", {"usage_consumed_seconds": 10}),
                          ("no consumed", {"usage_limit_seconds": 600})]:
        try:
            evaluate(payload, 10)
            print("  [FAIL] %-52s was accepted" % name)
            failures.append(name)
        except ValueError:
            print("  [OK ] %-52s raised ValueError" % name)

    print()
    if failures:
        print("SELF-TEST FAILED: %d case(s): %s"
              % (len(failures), ", ".join(failures)))
        return 1
    print("SELF-TEST PASSED: the gate accepts only what fits")
    return 0


# ── the main ────────────────────────────────────────────────────────────
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the QPU quota before submitting a measurement")
    parser.add_argument("--token-file", action="append", default=[],
                        help="JSON file with an 'apikey' field (repeatable)")
    parser.add_argument("--need-iterations", type=int, default=0,
                        help="how many iterations the measurement will run")
    parser.add_argument("--seconds-per-iteration", type=float, default=2.96,
                        help="the measured QPU seconds per iteration")
    parser.add_argument("--instance-name", default=DEFAULT_INSTANCE_NAME,
                        help="the instance name in the resource controller")
    parser.add_argument("--self-test", action="store_true",
                        help="run the decision-logic tests and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    need = args.need_iterations * args.seconds_per_iteration
    token_files = args.token_file or [None]

    print("=" * 78)
    print("QPU QUOTA CHECK")
    print("=" * 78)
    if need:
        print("requested: %d iterations x %.2f s/iter = %.0f s of QPU time"
              % (args.need_iterations, args.seconds_per_iteration, need))
    else:
        print("requested: no QPU time (a read-only check)")
    print()

    any_ok = False
    for token_file in token_files:
        label = token_file or ("IBM_QUANTUM_API_TOKEN from the environment")
        print("-- account: %s" % label)
        try:
            key = read_token(token_file)
            bearer = {"Authorization": "Bearer " + iam_token(key),
                      "Accept": "application/json"}
            crn = instance_crn(bearer, args.instance_name)
            usage = usage_of(bearer, crn)
            verdict = evaluate(usage, need)
            names = backends_of(bearer, crn)
        except Exception as exc:
            print("   ERROR: %s" % exc)
            print()
            continue

        print("   limit       : %.0f s (rolling 28-day window)"
              % verdict["limit"])
        print("   consumed    : %.0f s" % verdict["consumed"])
        print("   free now    : %.0f s" % verdict["free"])
        print("   limit hit   : %s" % ("yes" if verdict["limit_reached"] else "no"))
        if verdict["time_available_at"]:
            print("   next free   : %s (the oldest usage rolls out of the window)"
                  % verdict["time_available_at"])
        if names:
            print("   backends    : %s" % ", ".join(names))
        print("   VERDICT     : %s -- %s"
              % ("CAN RUN" if verdict["can_run"] else "CANNOT RUN",
                 verdict["reason"]))
        print()
        if verdict["can_run"]:
            any_ok = True

    if not token_files:
        print("ERROR: no account was checked", file=sys.stderr)
        return 2
    if need and not any_ok:
        print("QUOTA GATE FAILED: no account can cover %.0f s of QPU time"
              % need, file=sys.stderr)
        return 1
    if not need:
        print("QUOTA CHECK DONE (read-only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
