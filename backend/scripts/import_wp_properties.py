"""Import the website's available apartments into the backend.

Reads the public WordPress listings (the same ones classicjerusalem.com
shows) and creates a matching `Property` in the backend for each one that
is currently available. With `--photos`, it also copies each listing's
photo gallery into the connected Google Drive folder, exactly like the
admin's per-property photo upload does.

Idempotent: a listing already imported (matched by its `[wp-import id=N]`
notes marker) is skipped; a photo already uploaded (matched by per-property
checksum) is skipped. Safe to re-run — it resumes where it left off.

Scope: AVAILABLE listings only. Rented/sold listings and the
hide/uncategorized buckets are skipped.

Usage (from backend/):
    # 1. See exactly what WOULD happen — reads WP, writes nothing:
    uv run python scripts/import_wp_properties.py --dry-run

    # 2. Import listing data only (no photos):
    uv run python scripts/import_wp_properties.py

    # 3. Import data + copy photo galleries into Google Drive
    #    (Drive must be connected in Settings first):
    uv run python scripts/import_wp_properties.py --photos

Useful flags:
    --limit N                 only process the first N available listings
    --max-photos N            cap photos copied per listing (default: all)
    --enqueue                 also add each imported listing to the post queue

Point it at production by exporting the same DATABASE_URL / ENCRYPTION_KEY /
GOOGLE_OAUTH_* env the deployed backend uses (or run with backend/.env set
to production values).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import mimetypes
from collections import Counter

import httpx
from sqlalchemy import select

from shmuel_backend.cloud.crypto import decrypt
from shmuel_backend.cloud.drive import GoogleDriveStorage
from shmuel_backend.cloud.storage import CloudStorageError
from shmuel_backend.cloud_routes import (
    PROVIDER_GOOGLE,
    _property_folder_name,
)
from shmuel_backend.db import SessionLocal, engine
from shmuel_backend.models import CloudConnection, CloudPhoto, Property
from shmuel_backend.queue_routes import enqueue_property
from shmuel_backend.wp_import import (
    PlannedProperty,
    build_plan,
    fetch_all_properties,
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _print_plan(plan: list[PlannedProperty]) -> None:
    by_type: Counter[str] = Counter()
    total_photos = 0
    for p in plan:
        by_type[str(p.kwargs["type"])] += 1
        total_photos += len(p.photos)
    print(f"\nAvailable listings to import: {len(plan)}")
    for t, n in sorted(by_type.items()):
        print(f"  {t:>5}: {n}")
    print(f"Total gallery photos: {total_photos}")
    print("\nSample (first 8):")
    for p in plan[:8]:
        k = p.kwargs
        print(
            f"  wp#{p.wp_id:<5} {str(k['type']):>4}  "
            f"{str(k.get('neighborhood') or '?'):<16} "
            f"{str(k.get('address') or '?'):<18} "
            f"{k['price']} {k['currency']}  "
            f"rooms={k.get('rooms')}  sqm={k.get('size_sqm')}  "
            f"photos={len(p.photos)}"
        )
    no_photos = [p.wp_id for p in plan if not p.photos]
    if no_photos:
        print(f"\nListings with no photos ({len(no_photos)}): {no_photos}")


async def _import_metadata(
    plan: list[PlannedProperty], *, enqueue: bool
) -> dict[int, str]:
    """Create Property rows for not-yet-imported listings.

    Returns a {wp_id: property_id} map covering the whole plan (both rows
    created now and rows imported on a previous run), so the photo pass can
    attach galleries to all of them.
    """
    wp_id_to_pid: dict[int, str] = {}
    created = skipped = 0
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(Property.id, Property.notes))
        ).all()
        from shmuel_backend.wp_import import _IMPORT_MARKER_RE  # local import: test seam

        already: dict[int, str] = {}
        for pid, notes in existing:
            for m in _IMPORT_MARKER_RE.findall(notes or ""):
                already[int(m)] = str(pid)

        for p in plan:
            if p.wp_id in already:
                wp_id_to_pid[p.wp_id] = already[p.wp_id]
                skipped += 1
                continue
            prop = Property(**p.kwargs)
            session.add(prop)
            await session.flush()
            if enqueue:
                await enqueue_property(session, prop.id)
                await session.flush()  # so capacity spreading sees this slot
            await session.commit()
            wp_id_to_pid[p.wp_id] = str(prop.id)
            created += 1
    print(f"\nMetadata: created {created}, skipped (already imported) {skipped}")
    return wp_id_to_pid


async def _copy_photos(
    plan: list[PlannedProperty],
    wp_id_to_pid: dict[int, str],
    *,
    max_photos: int | None,
) -> None:
    storage = GoogleDriveStorage()
    async with SessionLocal() as session:
        conn = (
            await session.execute(
                select(CloudConnection).where(
                    CloudConnection.provider == PROVIDER_GOOGLE
                )
            )
        ).scalar_one_or_none()
        if conn is None or conn.root_folder_id is None:
            print(
                "\nGoogle Drive is NOT connected — skipping photos.\n"
                "Connect it in the admin Settings page, then re-run with --photos.\n"
                "(Listing data was still imported and is safe to keep.)"
            )
            return
        refresh_token = decrypt(conn.encrypted_refresh_token)

    uploaded = duplicate = failed = 0
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=True, headers={"user-agent": USER_AGENT}
    ) as http:
        for p in plan:
            pid = wp_id_to_pid.get(p.wp_id)
            if pid is None or not p.photos:
                continue
            async with SessionLocal() as session:
                prop = await session.get(Property, pid)
                if prop is None:
                    continue
                try:
                    folder = await storage.ensure_subfolder(
                        refresh_token, conn.root_folder_id, _property_folder_name(prop)
                    )
                except CloudStorageError as exc:
                    print(f"  wp#{p.wp_id}: folder error: {exc}")
                    failed += len(p.photos)
                    continue

                existing_sums = set(
                    (
                        await session.execute(
                            select(CloudPhoto.checksum).where(
                                CloudPhoto.property_id == prop.id
                            )
                        )
                    ).scalars().all()
                )

                photos = p.photos[:max_photos] if max_photos is not None else p.photos
                for ph in photos:
                    try:
                        resp = await http.get(ph.url)
                        resp.raise_for_status()
                        content = resp.content
                    except httpx.HTTPError as exc:
                        print(f"  wp#{p.wp_id}: download failed {ph.url}: {exc}")
                        failed += 1
                        continue
                    if not content:
                        failed += 1
                        continue
                    checksum = hashlib.sha256(content).hexdigest()
                    if checksum in existing_sums:
                        duplicate += 1
                        continue
                    mime = (
                        resp.headers.get("content-type", "").split(";")[0].strip()
                        or mimetypes.guess_type(ph.file_name)[0]
                        or "image/jpeg"
                    )
                    try:
                        f = await storage.upload_file(
                            refresh_token, folder.id, ph.file_name, content, mime
                        )
                    except CloudStorageError as exc:
                        print(f"  wp#{p.wp_id}: upload failed {ph.file_name}: {exc}")
                        failed += 1
                        continue
                    session.add(
                        CloudPhoto(
                            property_id=prop.id,
                            provider=PROVIDER_GOOGLE,
                            external_id=f.id,
                            folder_external_id=folder.id,
                            file_name=f.name,
                            mime_type=f.mime_type,
                            size_bytes=f.size_bytes,
                            checksum=checksum,
                            web_view_url=f.web_view_url,
                            thumbnail_url=f.thumbnail_url,
                        )
                    )
                    existing_sums.add(checksum)
                    await session.commit()
                    uploaded += 1
            print(f"  wp#{p.wp_id}: photos done ({len(photos)} in gallery)")
    print(
        f"\nPhotos: uploaded {uploaded}, already-present {duplicate}, failed {failed}"
    )


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="read WP, write nothing")
    ap.add_argument("--photos", action="store_true", help="copy galleries into Drive")
    ap.add_argument("--enqueue", action="store_true", help="add imports to the post queue")
    ap.add_argument("--limit", type=int, default=None, help="only first N listings")
    ap.add_argument("--max-photos", type=int, default=None, help="cap photos per listing")
    args = ap.parse_args()

    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True, headers={"user-agent": USER_AGENT}
    ) as http:
        rows = await fetch_all_properties(http)
    print(f"Fetched {len(rows)} WordPress listings.")
    plan = build_plan(rows, max_photos=args.max_photos)
    if args.limit is not None:
        plan = plan[: args.limit]
    _print_plan(plan)

    if args.dry_run:
        print("\n[dry-run] No database or Drive writes were made.")
        await engine.dispose()
        return

    try:
        wp_id_to_pid = await _import_metadata(plan, enqueue=args.enqueue)
        if args.photos:
            await _copy_photos(plan, wp_id_to_pid, max_photos=args.max_photos)
        else:
            print("\n(--photos not set: skipped copying galleries to Drive.)")
    finally:
        await engine.dispose()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
