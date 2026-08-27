package kr.co.axlink.project.web;

import java.util.List;
import java.util.UUID;

public record ProjectClosureResponse(
    UUID projectId,
    boolean closable,
    List<ClosureCheck> checks) {
}
