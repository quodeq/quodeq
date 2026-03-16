"""Re-export for backward compatibility — moved to quodeq.services.jobs."""
from quodeq.services.jobs import (  # noqa: F401
    Job,
    JobStore,
    InMemoryJobStore,
    create_job_store,
    JobManager,
    REPORT_PATH_RE,
)
