package kr.co.axlink.standard.domain;

import java.util.UUID;

public record TraceLinkDraft(
    TraceEntityType fromType,
    UUID fromId,
    TraceEntityType toType,
    UUID toId,
    TraceLinkKind linkKind) {
}
