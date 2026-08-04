# Release classification rules

These rules are versioned as `teacher-usability-v1` and must be frozen before study results are entered.

## Not ready

The stable synthetic evidence is incomplete or failing.

## Demo ready

The stable local synthetic evidence passes. Synthetic-only evidence can never exceed Demo ready.

## Controlled pilot ready

All of the following must be executed and evidenced: no open critical technical failures; privacy/security review complete; authorized non-production download and session smoke complete; physical printer evidence complete; and a real study with 3–5 teachers meeting the frozen thresholds.

## Pilot ready

Controlled pilot requirements plus production authentication, tenant isolation, private storage and download verification; backup/restore and rollback evidence; monitoring/support ownership; retention/deletion verification; and closure or explicit authorized acceptance of all high-severity findings.

## Frozen study thresholds

- Overall task completion: at least 90%.
- Critical tasks (print/download, start, record, recover, closeout): 100% completion.
- Median times: prepare ≤15 minutes; locate/print subset ≤2 minutes; start ≤1 minute; record one valid trial ≤20 seconds; recover ≤2 minutes; closeout ≤5 minutes.
- Worst case: no more than 2× the task threshold.
- Assisted or error tasks: at most 10%.
- Print readability and usefulness: median at least 4/5, with no critical unreadable output.
- Issues: zero critical and zero unresolved high-severity issues.
- Time saving: at least 80% of participants report saving time and the median estimated saving is at least 20% versus their current comparable workflow.

Raw observations, timings, and ratings remain separate from the release decision. A document, unchecked checklist, or BLOCKED check is not executed evidence.
