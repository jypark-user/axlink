package kr.co.axlink.integration.adapter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.co.axlink.common.error.ApiExceptions;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.port.ToolConnector;
import org.springframework.stereotype.Component;

@Component
public class ToolConnectorRegistry {

  private final Map<ToolType, ToolConnector> connectors;

  public ToolConnectorRegistry(List<ToolConnector> all) {
    Map<ToolType, ToolConnector> map = new LinkedHashMap<>();
    for (ToolConnector connector : all) {
      map.putIfAbsent(connector.tool(), connector);
    }
    this.connectors = Map.copyOf(map);
  }

  public ToolConnector require(ToolType tool) {
    ToolConnector connector = connectors.get(tool);
    if (connector == null) {
      throw ApiExceptions.toolUnreachable("지원하지 않는 도구 유형입니다: " + tool);
    }
    return connector;
  }
}
