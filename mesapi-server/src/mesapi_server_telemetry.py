"""
Telemetry management module for MES API Server.

Provides a wrapper class to configure and manage OpenTelemetry (OTel) 
logging. It facilitates the export of structured logs to an OTLP-compatible 
endpoint.
"""

import logging
from typing import Literal, Optional

from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter


internal_logger = logging.getLogger("mesapi-server-logger")

class MESAPIServerTelemetry:
    """
    Handler for OpenTelemetry logging exporting.

    Configures OpenTelemetry logger provider and integrates it with 
    Python's standard logging module to export structured logs to 
    an OTLP-compatible endpoint.

    Attributes:
        endpoint_host (str): Hostname or IP of the OTLP endpoint.
        endpoint_port (int): Port of the OTLP endpoint.
        service_name (str): Identifier for the service generating telemetry.
        deployment_environment (Literal["development", "production"]): 
            Target environment of the deployment.
        resource (Resource): OpenTelemetry resource containing metadata.
        otlp_endpoint (str): Formatted URL for the OTLP gRPC endpoint.
        logger_provider (LoggerProvider, optional): Internal provider for logs.
        is_initialized (bool): Flag indicating initialization status.
    """

    def __init__(
        self,
        endpoint_host: str,
        endpoint_port: int,
        service_name: str,
        deployment_environment: Literal["development", "production"]
    ) -> None:
        """
        Initialize the Telemetry object with the given configuration.

        Construct the OpenTelemetry Resource metadata and format 
        the OTLP endpoint URL.

        Args:
            endpoint_host (str): Network address of the OTLP collector.
            endpoint_port (int): Network port of the OTLP collector.
            service_name (str): Name of the service to attach to telemetry data.
            deployment_environment (Literal["development", "production"]): 
                Tag indicating the current environment.

        Returns:
            None

        Raises:
            ValueError: If the deployment_environment is not 'development' 
                or 'production'.
        """

        valid_deployment_envs = ["development", "production"]
        if deployment_environment not in valid_deployment_envs:
            raise ValueError(
                f"Invalid deployment environment '{deployment_environment}'. "
                f"Must be one of {valid_deployment_envs}"
            )

        self.endpoint_host = endpoint_host
        self.endpoint_port = endpoint_port
        self.service_name = service_name
        self.deployment_environment = deployment_environment

        self.resource = Resource.create({
            "service.name": self.service_name,
            "deployment.environment": self.deployment_environment
        })
        self.otlp_endpoint = f"http://{self.endpoint_host}:{self.endpoint_port}"

        self.logger_provider: Optional[LoggerProvider] = None
        self.is_initialized = False


    def setup(self) -> None:
        """
        Configure and initialize OpenTelemetry providers and exporters.

        Initialize the OTLP log exporter, configure the logger provider with
        batch log record processing, and integrate with Python's standard logging
        module. Skip if already initialized (idempotent). Initialization errors
        are caught and suppressed, leaving the instance uninitialized.

        Returns:
            None

        """

        if self.is_initialized:
            return
        
        try:
            # 1. LoggerProvider and log format setup
            logger_provider = LoggerProvider(self.resource)
            set_logger_provider(logger_provider)
            log_exporter = OTLPLogExporter(endpoint=f"{self.otlp_endpoint}/logs")
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

            log_format = f"MESAPI | %(message)s"
            formatter = logging.Formatter(log_format)

            # 2. Integrate OpenTelemetry with the standard Python logging module.
            # Attach the handler to the 'mesapi-server-logger' so that any standard log 
            # message is automatically converted and exported via OTLP.
            handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
            handler.setFormatter(formatter)
            edge_logger = logging.getLogger("mesapi-server-logger")
            edge_logger.addHandler(handler)
            edge_logger.setLevel(logging.INFO)
            edge_logger.propagate = False

            self.logger_provider = logger_provider
            self.is_initialized = True
        except Exception as e:
            self.shutdown()


    def shutdown(self) -> None:
        """
        Safely shut down the OpenTelemetry logger provider.

        When a provider exists, attempt to flush pending logs. Shut it down
        if flushing completes without raising. Suppress errors, then reset
        the provider reference and initialization flag in all cases.

        Returns:
            None

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
