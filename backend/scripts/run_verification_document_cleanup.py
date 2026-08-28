"""Run one bounded private verification-document cleanup batch.

This command never scans S3. It processes only tracked rows selected by status and
age, and the storage service rejects keys outside the configured private prefix.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.creator_verification_documents import cleanup_verification_documents  # noqa: E402
from app.services.verification_document_storage import (  # noqa: E402
    VerificationDocumentStorage,
    validate_verification_storage_configuration,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("admitly.verification_document_cleanup")


def main() -> int:
    validate_verification_storage_configuration()
    storage = VerificationDocumentStorage()
    with SessionLocal() as db:
        result = cleanup_verification_documents(db, storage=storage)
    logger.info(
        "verification_document_cleanup_complete selected=%d deleted=%d cleanup_required=%d",
        result["selected"],
        result["deleted"],
        result["cleanup_required"],
    )
    return 0 if result["cleanup_required"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
