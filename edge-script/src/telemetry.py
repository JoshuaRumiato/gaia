"""
Telemetry management module.

Provides a wrapper class to configure and manage OpenTelemetry (OTel) 
metrics and logging. It facilitates the export of system metrics, 
custom metrics, and structured logs to an OTLP-compatible endpoint.
"""

import logging
import asyncio
from typing import Literal, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

internal_logger = logging.getLogger("edge-logger")

class Telemetry:
    """Handler for OpenTelemetry metrics and logs exporting.

    Configures OpenTelemetry providers, instruments system metrics,
    and establishes a custom observable gauge to monitor the status 
    of an asynchronous message queue.

    Attributes:
        endpoint_host (str): Hostname or IP of the OTLP endpoint.
        endpoint_port (int): Port of the OTLP endpoint.
        service_name (str): Identifier for the service generating telemetry.
        deployment_environment (Literal["development", "production"]): 
            Target environment of the deployment.
        hostname (str): Unique identifier for the host device.
        queue (asyncio.Queue): Asynchronous queue to monitor its size.
        resource (Resource): OpenTelemetry resource containing metadata.
        otlp_endpoint (str): Formatted URL for the OTLP gRPC endpoint.
        logger_provider (LoggerProvider, optional): Internal provider for logs.
        meter_provider (MeterProvider, optional): Internal provider for metrics.
    """

    def __init__(
        self,
        endpoint_host: str,
        endpoint_port: int,
        service_name: str,
        deployment_environment: Literal["development", "production"],
        hostname: str,
        queue: asyncio.Queue
    ) -> None:
        """Initialize the Telemetry object with the given configuration.

        Construct the OpenTelemetry Resource metadata and format 
        the OTLP endpoint URL.

        Args:
            endpoint_host (str): Network address of the OTLP collector.
            endpoint_port (int): Network port of the OTLP collector.
            service_name (str): Name of the service to attach to telemetry data.
            deployment_environment (Literal["development", "production"]): 
                Tag indicating the current environment.
            hostname (str): Unique client identifier (e.g., Hostname + MAC).
            queue (asyncio.Queue): Asyncio queue to be monitored by custom metrics.

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
        self.queue = queue
        self.resource = Resource.create({
            "service.name": self.service_name,
            "deployment.environment": self.deployment_environment,
            "host.name": self.hostname
        })
        self.otlp_endpoint = f"http://{self.endpoint_host}:{self.endpoint_port}"

        self.logger_provider: Optional[LoggerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.is_initialized = False


    def setup(self) -> None:
        """Configure and start the OpenTelemetry providers and exporters.

        Perform the following initialization steps:
        - Set up the LoggerProvider with an OTLP gRPC exporter.
        - Configure the standard Python logging module to route 'edge-logger' 
          logs through OpenTelemetry.
        - Set up the MeterProvider with a periodic OTLP exporter.
        - Start the SystemMetricsInstrumentor to capture hardware metrics.
        - Register a custom observable gauge for monitoring the size 
          of the provided asynchronous queue.

        Returns:
            None

        Raises:
            Exception: If any part of the initialization fails, the error is 
                caught, and a shutdown is attempted to ensure partial 
                resources are cleaned up.
        """

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
            edge_logger = logging.getLogger("edge-logger")
            edge_logger.addHandler(handler)
            edge_logger.setLevel(logging.INFO)
            edge_logger.propagate = False
            
            # 3. Metrics setup
            metric_exporter = OTLPMetricExporter(endpoint=f"{self.otlp_endpoint}/metrics")
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
            meter_provider = MeterProvider(resource=self.resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)

            # 4. Start SystemMetricsInstrumentor to automatically collect and export standard host metrics
            SystemMetricsInstrumentor().instrument()
            
            # 5. Create a custom metric to monitor the internal data queue size
            meter = metrics.get_meter("edge-queue-metrics")
            meter.create_observable_gauge(
                name="queue_size",
                callbacks=[lambda options: [metrics.Observation(self.queue.qsize())]],
                description="No. of messagges waiting to be published",
                unit="1"
            )

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
            if self.meter_provider:
                self.meter_provider.force_flush()
                self.meter_provider.shutdown()
        except Exception as e:
            pass
            # internal_logger.error(f"Failed to shutdown telemetry: {e}")
        finally:
            self.logger_provider = None
            self.meter_provider = None
            self.is_initialized = False
