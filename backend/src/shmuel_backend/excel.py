from collections.abc import Callable
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from shmuel_backend.models import Property

Column = tuple[str, Callable[[Property], Any]]

COLUMNS: list[Column] = [
    ("ID", lambda p: str(p.id)),
    ("Type", lambda p: p.type.value),
    ("Status", lambda p: p.status.value),
    ("Price", lambda p: float(p.price)),
    ("Currency", lambda p: p.currency),
    ("Rooms", lambda p: float(p.rooms) if p.rooms is not None else None),
    ("Size (sqm)", lambda p: p.size_sqm),
    ("Floor", lambda p: p.floor),
    ("Address", lambda p: p.address),
    ("Neighborhood", lambda p: p.neighborhood),
    ("City", lambda p: p.city),
    ("Owner name", lambda p: p.owner_name),
    ("Owner phone", lambda p: p.owner_phone),
    ("Broker fee", lambda p: p.broker_fee_status.value),
    (
        "Broker fee amount",
        lambda p: float(p.broker_fee_amount)
        if p.broker_fee_amount is not None
        else None,
    ),
    ("Description", lambda p: p.description),
    ("Notes", lambda p: p.notes),
    ("Yad2 URL", lambda p: p.yad2_url),
    ("Created at", lambda p: p.created_at),
    ("Updated at", lambda p: p.updated_at),
]


def properties_to_xlsx(rows: list[Property]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Properties"
    ws.append([c[0] for c in COLUMNS])
    for p in rows:
        ws.append([c[1](p) for c in COLUMNS])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
