import logging

from triton.triton import run_triton

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

OTHER_LOGGERS = [
    "httpx",
    "apscheduler.scheduler",
    "apscheduler.executors",
    "apscheduler.executors.default",
    "telegram.ext.Application",
]

# Lower other loggers logging level to reduce log pollution
for logger_name in OTHER_LOGGERS:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

if __name__ == "__main__":
    run_triton()
