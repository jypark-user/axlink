package kr.co.axlink.integration.port;

import kr.co.axlink.integration.domain.ToolType;

public interface ToolConnector {

  ToolType tool();

  ToolConnectorTypes.ToolProbe verify(ToolConnectorTypes.ToolConnectionSpec spec);

  ToolConnectorTypes.FetchPage fetch(ToolConnectorTypes.ToolConnectionSpec spec,
      ToolConnectorTypes.FetchCursor cursor);
}
