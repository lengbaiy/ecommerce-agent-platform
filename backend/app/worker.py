import logging
from os import getenv
from time import sleep

from app.api.dependencies import get_task_service
from app.core import settings
from app.main import configure_logging

logger = logging.getLogger("app.worker")


def main() -> None:
    settings.validate()
    configure_logging()
    service = get_task_service()
    poll_interval = float(getenv("WORKER_POLL_INTERVAL_SECONDS", "1"))
    logger.info("agent worker started environment=%s", settings.environment)
    while True:
        try:
            task = service.run_next()
            if task is None:
                sleep(poll_interval)
            else:
                logger.info(
                    "task executed task_id=%s tenant_id=%s status=%s",
                    task.id,
                    task.request.tenant_id,
                    task.status,
                )
        except Exception:
            logger.exception("worker task execution failed")
            sleep(poll_interval)


if __name__ == "__main__":
    main()
