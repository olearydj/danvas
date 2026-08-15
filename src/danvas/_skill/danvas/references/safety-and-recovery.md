# Danvas Safety And Recovery

## Authorization

Canvas mutation is plan-by-default. Only `--apply` authorizes the reviewed write.
Some operations also require the exact `--confirm` value shown by help. No
profile, project setting, or environment variable can restore mutation on
omission.

Local-write commands are distinct. Their `--dry-run` previews local creation;
they never use `--apply` and retain no authority to change Canvas.

Missing danvas coverage is not authorization to switch to direct Canvas API,
browser automation, or provider-specific tooling. Classify the endpoint effect
and ask the operator before leaving the reviewed interface.

## Evidence

Distinguish at least:

- planned or skipped: no Canvas write attempted;
- applied and verified: authoritative evidence matches;
- rejected or failed before acceptance: safe only after correcting the cause;
- accepted but unverified: Canvas may have accepted the write;
- conflict: current state or duplicate policy blocks the intended action; and
- indeterminate: available evidence cannot support a success/failure claim.

Transport acceptance alone is not verification. Use retained row/bundle evidence
and command-specific readback.

## Stop Rules

After accepted-unverified or indeterminate evidence:

1. stop new writes;
2. do not rerun blindly;
3. inspect the private results and recovery guidance;
4. read current Canvas state with a bounded command where safe; and
5. replan only after the expected-state guard can be represented honestly.

Do not delete conflicting local files merely to make a sync or download pass.
Move an interrupted artifact aside only when help says that is the recovery
boundary.
