# `negation/` — Track C

The negation engine. Evaluates *what must not exist*: the intersection of the
observed semantic state `S` with the negative constraint set `C`, plus a
cross-check pass to suppress false positives.

**Owner:** Track C. Track B passes `(S_current, C_negative)` through
`PerceptionPort.audit()` and consumes the returned `Violation` list.
