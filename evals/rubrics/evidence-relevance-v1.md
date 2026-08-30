# Evidence Relevance Rubric v1

Annotate relevance for one atomic Job Requirement against stable EvidenceItem IDs. Review the human-confirmed Evidence content and provenance; never infer a supporting fact that the Evidence does not state.

- `DIRECT`: the Evidence explicitly supports the Requirement or a concrete instance of it.
- `PARTIAL`: the Evidence supports a material subset or closely related capability but leaves a meaningful gap.
- `BACKGROUND`: the Evidence supplies useful context but does not establish that the Requirement is met.

Assign positive judgments only to Evidence in the case's complete eligible set after validity and allowed-sensitivity filtering. Use `no_relevant_evidence=true` only after a human reviews that complete eligible set and explicitly confirms that no item reaches any relevance grade. An empty judgment list alone is not a No-Evidence annotation. Multiple EvidenceItems may receive labels for one Requirement.

Record uncertain annotation decisions for review instead of forcing a positive label. Frozen Holdout annotations must not be changed for targeted tuning; a tuned case moves to Development and is replaced.
