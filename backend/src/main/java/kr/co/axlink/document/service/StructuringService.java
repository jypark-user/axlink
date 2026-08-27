package kr.co.axlink.document.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.ai.port.LlmMessage;
import kr.co.axlink.ai.port.LlmModels;
import kr.co.axlink.ai.port.LlmPort;
import kr.co.axlink.ai.port.LlmRequest;
import kr.co.axlink.ai.port.ToolInvocation;
import kr.co.axlink.ai.port.ToolRequest;
import kr.co.axlink.ai.port.ToolSchema;
import kr.co.axlink.ai.prompt.Prompts;
import kr.co.axlink.ai.prompt.ToolNames;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.document.domain.DocumentUpload;
import kr.co.axlink.document.domain.DocumentUploadStatus;
import kr.co.axlink.document.domain.StructuringDraft;
import kr.co.axlink.document.repository.DocumentUploadRepository;
import kr.co.axlink.document.repository.StructuringDraftRepository;
import kr.co.axlink.document.web.DocumentDtos.DraftRequirement;
import kr.co.axlink.document.web.DocumentDtos.StructuringDraftResponse;
import kr.co.axlink.integration.port.WorkProductType;
import kr.co.axlink.standard.domain.PmActivity;
import kr.co.axlink.standard.domain.RequirementPriority;
import kr.co.axlink.standard.domain.SiActivity;
import org.springframework.stereotype.Service;

@Service
public class StructuringService {

  private static final List<String> WP_TYPES = Arrays.stream(WorkProductType.values())
      .map(Enum::name).toList();

  private final LlmPort llmPort;
  private final LlmModels llmModels;
  private final DocumentUploadRepository uploadRepository;
  private final StructuringDraftRepository draftRepository;
  private final ProjectAccessResolver accessResolver;

  public StructuringService(LlmPort llmPort, LlmModels llmModels,
      DocumentUploadRepository uploadRepository, StructuringDraftRepository draftRepository,
      ProjectAccessResolver accessResolver) {
    this.llmPort = llmPort;
    this.llmModels = llmModels;
    this.uploadRepository = uploadRepository;
    this.draftRepository = draftRepository;
    this.accessResolver = accessResolver;
  }

  public void structure(UUID documentUploadId, String text, Integer pageCount) {
    if (text == null || text.isBlank()) {
      uploadRepository.updateStatus(documentUploadId, DocumentUploadStatus.STRUCTURED, null);
      draftRepository.insert(documentUploadId, llmModels.structuring(),
          emptyDraft(), null, true);
      return;
    }
    ToolSchema schema = new ToolSchema(ToolNames.STRUCTURE_WORK_PRODUCT,
        "산출물 문서를 정형화 데이터로 추출한다.", parameters());
    LlmRequest base = LlmRequest.of(llmModels.structuring(),
        List.of(LlmMessage.system(Prompts.STRUCTURING_SYSTEM),
            LlmMessage.user(truncate(text, 24000))));
    ToolInvocation invocation;
    try {
      invocation = llmPort.callTool(new ToolRequest(base, schema));
    } catch (RuntimeException e) {
      throw ApiExceptions.aiToolCallFailed("정형화 도구 호출 실패: " + e.getMessage());
    }
    if (!invocation.isPresent()) {
      throw ApiExceptions.aiToolCallFailed("정형화 도구 응답이 비어 있습니다.");
    }
    JsonNode args = invocation.arguments();
    WorkProductType type = parseType(args.path("type").asText(null));
    boolean typeRejected = type == null && args.path("type").asText(null) != null;
    draftRepository.insert(documentUploadId, llmModels.structuring(),
        invocation.arguments(), type, typeRejected);
    uploadRepository.updateStatus(documentUploadId, DocumentUploadStatus.STRUCTURED, null);
  }

  public StructuringDraftResponse draft(UUID documentId, AuthPrincipal principal) {
    DocumentUpload doc = uploadRepository.findById(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("document", documentId));
    accessResolver.requireProject(principal, doc.projectId());
    if (doc.status() != DocumentUploadStatus.STRUCTURED
        && doc.status() != DocumentUploadStatus.CONFIRMED
        && doc.status() != DocumentUploadStatus.REJECTED) {
      throw ApiExceptions.notFound("structuring_draft", documentId);
    }
    StructuringDraft draft = draftRepository.findByDocumentUploadId(documentId)
        .orElseThrow(() -> ApiExceptions.notFound("structuring_draft", documentId));
    return toDraftResponse(documentId, draft);
  }

  StructuringDraftResponse toDraftResponse(UUID documentId, StructuringDraft draft) {
    JsonNode args = draft.draftJson();
    return new StructuringDraftResponse(documentId, draft.status(), draft.proposedType(),
        draft.typeRejected() ? args.path("type").asText(null) : null,
        args.path("confidence").asDouble(0.0), nullable(args.path("title").asText(null)),
        nullable(args.path("version").asText(null)), parseDate(args.path("authoredDate").asText(null)),
        parseEnum(args.path("pmActivity").asText(null), PmActivity.class),
        parseEnum(args.path("siActivity").asText(null), SiActivity.class),
        parseRequirements(args.path("requirements")), draft.createdAt());
  }

  List<DraftRequirement> parseRequirements(JsonNode node) {
    if (node == null || !node.isArray()) {
      return List.of();
    }
    List<DraftRequirement> out = new ArrayList<>();
    for (int i = 0; i < node.size(); i++) {
      JsonNode item = node.get(i);
      out.add(new DraftRequirement(i, nullable(item.path("code").asText(null)),
          item.path("title").asText(""), item.path("body").asText(""),
          parseEnum(item.path("priority").asText(null), RequirementPriority.class)));
    }
    return out;
  }

  static WorkProductType parseType(String raw) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    try {
      return WorkProductType.valueOf(raw.trim().toUpperCase());
    } catch (IllegalArgumentException e) {
      return null;
    }
  }

  static <E extends Enum<E>> E parseEnum(String raw, Class<E> type) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    try {
      return Enum.valueOf(type, raw.trim().toUpperCase());
    } catch (IllegalArgumentException e) {
      return null;
    }
  }

  static LocalDate parseDate(String raw) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    try {
      return LocalDate.parse(raw.trim().substring(0, Math.min(10, raw.trim().length())));
    } catch (Exception e) {
      return null;
    }
  }

  private static String nullable(String v) {
    return v == null || v.isBlank() ? null : v;
  }

  private static String truncate(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max);
  }

  private static com.fasterxml.jackson.databind.node.ObjectNode emptyDraft() {
    return new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode();
  }

  private static Map<String, Object> parameters() {
    List<String> priorities = Arrays.stream(RequirementPriority.values()).map(Enum::name).toList();
    List<String> pm = Arrays.stream(PmActivity.values()).map(Enum::name).toList();
    List<String> si = Arrays.stream(SiActivity.values()).map(Enum::name).toList();
    Map<String, Object> type = new LinkedHashMap<>();
    type.put("type", "string");
    type.put("enum", WP_TYPES);
    Map<String, Object> title = str();
    Map<String, Object> version = str();
    Map<String, Object> authored = str();
    Map<String, Object> pmField = new LinkedHashMap<>();
    pmField.put("type", "string");
    pmField.put("enum", pm);
    Map<String, Object> siField = new LinkedHashMap<>();
    siField.put("type", "string");
    siField.put("enum", si);
    Map<String, Object> confidence = new LinkedHashMap<>();
    confidence.put("type", "number");
    Map<String, Object> reqCode = str();
    Map<String, Object> reqTitle = str();
    Map<String, Object> reqBody = str();
    Map<String, Object> reqPriority = new LinkedHashMap<>();
    reqPriority.put("type", "string");
    reqPriority.put("enum", priorities);
    Map<String, Object> reqItem = new LinkedHashMap<>();
    reqItem.put("type", "object");
    reqItem.put("properties", Map.of("code", reqCode, "title", reqTitle, "body", reqBody,
        "priority", reqPriority));
    reqItem.put("required", List.of("title", "body"));
    Map<String, Object> reqArray = new LinkedHashMap<>();
    reqArray.put("type", "array");
    reqArray.put("items", reqItem);
    Map<String, Object> props = new LinkedHashMap<>();
    props.put("type", type);
    props.put("title", title);
    props.put("version", version);
    props.put("authoredDate", authored);
    props.put("pmActivity", pmField);
    props.put("siActivity", siField);
    props.put("confidence", confidence);
    props.put("requirements", reqArray);
    Map<String, Object> schema = new LinkedHashMap<>();
    schema.put("type", "object");
    schema.put("properties", props);
    schema.put("required", List.of("type", "requirements"));
    return schema;
  }

  private static Map<String, Object> str() {
    return new LinkedHashMap<>(Map.of("type", "string"));
  }
}
