"""Entry point: python -m fraud_scoring"""

import logging
import sys

from fraud_scoring import config, metrics
from fraud_scoring.consumer import run


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s [fraud-scoring] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    settings = config.from_env()
    metrics.serve(settings.metrics_port)
    run(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
