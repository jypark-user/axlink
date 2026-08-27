package kr.co.axlink.document.domain;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.UUID;
import kr.co.axlink.integration.port.WorkProductType;

public record StructuringDraft(
    UUID id, UUID documentUploadId, String model, JsonNode draftJson, WorkProductType proposedType,
    boolean typeRejected, StructuringDraftStatus status, UUID confirmedByUserId, Instant confirmedAt,
    UUID workProductId, Instant createdAt, Instant updatedAt) {}
