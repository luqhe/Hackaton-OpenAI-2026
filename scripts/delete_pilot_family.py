from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.storage import GuardianStore  # noqa: E402
from guardian_core.models import FamilyDeletionReceipt  # noqa: E402


def delete_with_confirmation(
    store: GuardianStore, family_id: str, confirmation: str
) -> FamilyDeletionReceipt:
    if confirmation != family_id:
        raise ValueError("--confirm-family-id must exactly match --family-id")
    return store.delete_family(family_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete one family from the local Guardian store")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--family-id")
    operation.add_argument("--resume-receipt")
    parser.add_argument("--confirm-family-id")
    parser.add_argument("--confirm-receipt-id")
    args = parser.parse_args()

    database = args.database.resolve()
    evidence_directory = args.evidence_directory.resolve()
    store = GuardianStore(database, evidence_directory)
    store.initialize()
    try:
        if args.resume_receipt is not None:
            if args.confirm_receipt_id != args.resume_receipt:
                raise ValueError("--confirm-receipt-id must exactly match --resume-receipt")
            receipt = store.resume_family_deletion(args.resume_receipt)
        else:
            receipt = delete_with_confirmation(store, args.family_id, args.confirm_family_id or "")
    except (KeyError, OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
