package kr.co.axlink.integration.service;

import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.auth.security.ProjectAccessResolver;
import kr.co.axlink.integration.adapter.ToolConnectorRegistry;
import kr.co.axlink.integration.domain.ToolConnection;
import kr.co.axlink.integration.domain.ToolType;
import kr.co.axlink.integration.port.ToolConnector;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolConnectionSpec;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolCredential;
import kr.co.axlink.integration.port.ToolConnectorTypes.ToolProbe;
import org.springframework.stereotype.Service;

@Service
public class ToolConnectionTestService {

  private final ToolConnectorRegistry connectorRegistry;
  private final ToolConnectionService connectionService;
  private final ToolConnectionSecretProvider secretProvider;
  private final ProjectAccessResolver accessResolver;

  public ToolConnectionTestService(ToolConnectorRegistry connectorRegistry,
      ToolConnectionService connectionService, ToolConnectionSecretProvider secretProvider,
      ProjectAccessResolver accessResolver) {
    this.connectorRegistry = connectorRegistry;
    this.connectionService = connectionService;
    this.secretProvider = secretProvider;
    this.accessResolver = accessResolver;
  }

  public ToolProbe test(ToolType tool, String baseUrl, String targetResource,
      ToolCredential credential) {
    ToolConnector connector = connectorRegistry.require(tool);
    return connector.verify(new ToolConnectionSpec(tool, baseUrl, targetResource, credential));
  }

  public ToolProbe testSaved(UUID connectionId, AuthPrincipal principal) {
    ToolConnection connection = connectionService.findOrThrow(connectionId);
    accessResolver.requireProject(principal, connection.projectId());
    ToolCredential credential = secretProvider.decrypt(connection);
    return test(connection.tool(), connection.baseUrl(), connection.targetResource(), credential);
  }
}
