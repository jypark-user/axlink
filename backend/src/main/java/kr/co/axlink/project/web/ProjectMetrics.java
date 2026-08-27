package kr.co.axlink.project.web;

import java.time.Instant;

public record ProjectMetrics(
    long requirementTotal,
    long requirementAccepted,
    long issueOpen,
    long riskOpen,
    long workProductApproved,
    long workProductTotal,
    int traceabilityCoverage,
    Instant lastSyncedAt) {
}
