"""
Telemetry management module.

Provides a wrapper class to configure and manage OpenTelemetry (OTel) 
metrics and logging. It facilitates the export of system metrics, 
custom metrics, and structured logs to an OTLP-compatible endpoint.
"""

import logging
from typing import Literal, Optional

from opentelemetry.sdk.resources import Resource
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

internal_logger = logging.getLogger("opcua-server-logger")

class OPCServerTelemetry:

    def __init__(
        self,
        endpoint_host: str,
        endpoint_port: int,
        service_name: str,
        deployment_environment: Literal["development", "production"],
        hostname: str,
    ) -> None:

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
        if self.is_initialized:
            # internal_logger.warning("Telemetry already initalized.")
            return
        
        try:
            # 1. LoggerProvider and log format setup
            logger_provider = LoggerProvider(self.resource)
            set_logger_provider(logger_provider)
            log_exporter = OTLPLogExporter(endpoint=f"{self.otlp_endpoint}/logs")
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

            log_format = f"MAIA | {self.hostname} | %(message)s"
            formatter = logging.Formatter(log_format)

            # 2. Integrate OpenTelemetry with the standard Python logging module.
            # Attach the handler to the 'edge-logger' so that any standard log 
            # message is automatically converted and exported via OTLP.
            handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
            handler.setFormatter(formatter)
            edge_logger = logging.getLogger("opcua-server-logger")
            edge_logger.addHandler(handler)
            edge_logger.setLevel(logging.INFO)
            edge_logger.propagate = False

            self.is_initialized = True
            # internal_logger.info("Telemetry successfully initialized.")
        except Exception as e:
            # internal_logger.error(f"Failed to initialize telemetry: {e}")
            self.shutdown()


    def shutdown(self) -> None:
        """Safely shut down the OpenTelemetry providers.

        Ensure that all pending logs and metrics are flushed to the 
        configured endpoints before the application instance is destroyed.
        Reset the provider attributes and the initialization flag.

        Returns:
            None

        Raises:
            Exception: Internal errors during the flushing or shutdown process 
                are caught and suppressed to prevent interruption of the 
                application's exit sequence.
        """

        try:
            if self.logger_provider:
                self.logger_provider.force_flush()
                self.logger_provider.shutdown()
        except Exception as e:
            pass
            # internal_logger.error(f"Failed to shutdown telemetry: {e}")
        finally:
            self.logger_provider = None
            self.is_initialized = False
