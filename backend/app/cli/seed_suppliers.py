from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.core.database import async_session_maker
from app.models.entities import Supplier


async def seed_suppliers_from_manifest(manifest_path: str) -> int:
    path = Path(manifest_path)
    if not path.exists():
        print(f"Manifest file '{path}' does not exist.")
        return 0

    suppliers: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            gstin = item.get("supplier_gstin")
            name = item.get("supplier_name")
            if gstin and name:
                suppliers[gstin.strip().upper()] = name.strip()

    print(f"Extracted {len(suppliers)} unique suppliers from {path}...")

    async with async_session_maker() as session:
        count = 0
        for gstin, name in suppliers.items():
            state_code = gstin[:2]
            stmt = (
                insert(Supplier)
                .values(
                    id=uuid.uuid4(),
                    gstin=gstin,
                    name=name,
                    state_code=state_code,
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["gstin"],
                    set_={
                        "name": name,
                        "state_code": state_code,
                        "is_active": True,
                    },
                )
            )
            await session.execute(stmt)
            count += 1

        await session.commit()
        print(f"Successfully upserted {count} suppliers into database.")
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed suppliers into database")
    parser.add_argument(
        "--manifest",
        type=str,
        default="manifest.jsonl",
        help="Path to manifest.jsonl",
    )
    args = parser.parse_args()

    asyncio.run(seed_suppliers_from_manifest(args.manifest))


if __name__ == "__main__":
    main()

