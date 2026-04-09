"""
Trinity — Tracing Utilities
Central tracer factory for manual span instrumentation across the codebase.
"""

from opentelemetry import trace


def get_tracer(name: str = "triageforge") -> trace.Tracer:
    """
    Get a named tracer instance from the global TracerProvider.
    
    Usage:
        tracer = get_tracer("triageforge.pipeline")
        with tracer.start_as_current_span("my_operation") as span:
            span.set_attribute("key", "value")
    """
    return trace.get_tracer(name, "1.0.0")
