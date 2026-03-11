import math
from sqlalchemy.orm import Session
from models import Ticket, Detection


def haversine_distance(lat1, lng1, lat2, lng2) -> float:
    """Returns distance in meters between two GPS coordinates."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def mock_reverse_geocode(lat: float, lng: float) -> str:
    """Mock reverse geocode for Tel Aviv streets."""
    streets = [
        (32.0800, 34.7800, "Dizengoff St"),
        (32.0820, 34.7780, "Ibn Gabirol St"),
        (32.0650, 34.7750, "Rothschild Blvd"),
        (32.0680, 34.7700, "Allenby St"),
        (32.0770, 34.7720, "King George St"),
        (32.0890, 34.7670, "HaYarkon St"),
        (32.0750, 34.7800, "Ben Yehuda St"),
        (32.0720, 34.7850, "Herzl St"),
    ]
    closest = min(streets, key=lambda s: haversine_distance(lat, lng, s[0], s[1]))
    number = int(abs(lat * 1000) % 120) + 1
    return f"{closest[2]} {number}, Tel Aviv"


def find_or_create_ticket(db: Session, detection_data: dict) -> tuple[Ticket, bool]:
    """
    Check if open ticket exists within 30m for same defect type.
    Returns (ticket, is_new).
    """
    lat = detection_data["lat"]
    lng = detection_data["lng"]
    defect_type = detection_data["defect_type"]

    open_statuses = ["new", "verified", "assigned", "in_progress"]
    candidates = db.query(Ticket).filter(
        Ticket.defect_type == defect_type,
        Ticket.status.in_(open_statuses)
    ).all()

    for ticket in candidates:
        dist = haversine_distance(lat, lng, ticket.lat, ticket.lng)
        if dist <= 30:
            # Merge into existing ticket
            ticket.detection_count += 1
            ids = list(ticket.vehicle_ids or [])
            vid = detection_data.get("vehicle_id", "")
            if vid and vid not in ids:
                ids.append(vid)
            ticket.vehicle_ids = ids
            db.commit()
            db.refresh(ticket)
            return ticket, False

    # Create new ticket
    address = mock_reverse_geocode(lat, lng)
    ticket = Ticket(
        defect_type=defect_type,
        severity=detection_data["severity"],
        lat=lat,
        lng=lng,
        address=address,
        status="new",
        detection_count=1,
        vehicle_ids=[detection_data.get("vehicle_id", "")]
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket, True
