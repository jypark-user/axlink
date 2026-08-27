package kr.co.axlink.standard.domain;

public enum SourceKind {
  TOOL, DOCUMENT, MANUAL;

  public static SourceKind resolve(Boolean fromTool, Boolean fromDocument) {
    if (fromTool != null && fromTool) {
      return TOOL;
    }
    if (fromDocument != null && fromDocument) {
      return DOCUMENT;
    }
    return MANUAL;
  }
}
