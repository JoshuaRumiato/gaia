"""
Telemetry management module for OpenTelemetry integration.

Provides a wrapper class to configure and manage OpenTelemetry (OTel)
logging. Facilitates the export of structured logs to an OTLP-compatible
endpoint and integrates with Python's standard logging module.
"""

import logging
from typing import Literal, Optional

from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

internal_logger = logging.getLogger("gateway-logger")

class GatewayTelemetry:
    """
    Manages OpenTelemetry logging for gateway services.
    
    Configures OpenTelemetry providers and integrates with the standard
    Python logging module to export structured logs to an OTLP-compatible
    endpoint.

    Attributes:
        endpoint_host: Hostname or IP of the OTLP endpoint.
        endpoint_port: Port of the OTLP endpoint.
        service_name: Identifier for the service generating telemetry.
        deployment_environment: Target environment ('development' or 'production').
        hostname: Unique identifier for the host device.
        resource: OpenTelemetry resource containing metadata.
        otlp_endpoint: Formatted URL for the OTLP gRPC endpoint.
        logger_provider: Internal provider for logs (None until initialized).
        is_initialized: Boolean indicating initialization status.
    """

    def __init__(
        self,
        endpoint_host: str,
        endpoint_port: int,
        service_name: str,
        deployment_environment: Literal["development", "production"],
        hostname: str
    ) -> None:
        """
        Initialize the GatewayTelemetry object.

        Construct the OpenTelemetry Resource metadata and format 
        the OTLP endpoint URL for later initialization.

        Args:
            endpoint_host (str): Network address of the OTLP collector.
            endpoint_port (int): Network port of the OTLP collector.
            service_name (str): Name of the service to attach to telemetry data.
            deployment_environment (Literal["development", "production"]): Tag indicating the current environment.
            hostname (str): Unique client identifier (e.g., hostname or hostname+MAC).

        Returns:
            None

        Raises:
            ValueError: If the deployment_environment is not 'development' 
                or 'production'.
        """

        valid_deployment_envs = ["development", "production"]
        if deployment_environment not in valid_deployment_envs:
            raise ValueError(f"Invalid deployment environment '{deployment_environment}'. Must be one of {valid_deployment_envs}")

        self.endpoint_host = endpoint_host
        self.endpoint_port = endpoint_port
        self.service_name = service_name
        self.deployment_environment = deployment_environment
        self.hostname = hostname
        self.resource = Resource.create({
            "service.name": self.service_name,
            "deployment.environment": self.deployment_environment,
            "host.name": self.hostname
        })
        self.otlp_endpoint = f"http://{self.endpoint_host}:{self.endpoint_port}"

        self.logger_provider: Optional[LoggerProvider] = None
        self.is_initialized = False


    def setup(self) -> None:
        """
        Configure and initialize OpenTelemetry providers and exporters.

        Perform initialization steps:
        - Set up LoggerProvider with OTLP gRPC exporter
        - Configure Python logging module to route gateway logs through OTel
        - Skip if already initialized (idempotent)

        Returns:
            None

        Raises:
            Exception: Errors are caught and logged; shutdown is called to
                clean up any partially initialized resources.
        """

        if self.is_initialized:
            return
        
        try:
            # Set up LoggerProvider and log format
            logger_provider = LoggerProvider(self.resource)
            set_logger_provider(logger_provider)
            log_exporter = OTLPLogExporter(endpoint=f"{self.otlp_endpoint}/logs")
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

            log_format = f"GAIA | {self.hostname} | %(message)s"
            formatter = logging.Formatter(log_format)

            # Integrate with standard Python logging module
            handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
            handler.setFormatter(formatter)
            gateway_logger = logging.getLogger("gateway-logger")
            gateway_logger.addHandler(handler)
            gateway_logger.setLevel(logging.INFO)
            gateway_logger.propagate = False
            
            self.logger_provider = logger_provider
            self.is_initialized = True
        except Exception as e:
            self.shutdown()


    def shutdown(self) -> None:
        """
        Safely shut down OpenTelemetry providers.

        Ensure that all pending logs are flushed to the configured endpoint
        before the application instance is destroyed. Reset the provider
        attributes and the initialization flag.

        Returns:
            None

        Raises:
            Exception: Errors during flushing or shutdown are caught and
                suppressed to prevent interruption of exit sequence.
        """

        try:
            if self.logger_provider:
                self.logger_provider.force_flush()
                self.logger_provider.shutdown()
        except Exception as e:
            pass
        finally:
            self.logger_provider = None
            self.is_initialized = False
