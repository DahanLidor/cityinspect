"""Seed realistic demo data for CityInspect across Kfar Saba & HaSharon area."""
import requests, random, time

API = "http://localhost:8000/api/v1"

# Login
r = requests.post(f"{API}/login", json={"username": "admin", "password": "changeme123"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Realistic locations around Kfar Saba, Ra'anana, Hod HaSharon, Herzliya
LOCATIONS = [
    (32.1780, 34.9075, "רח׳ ויצמן, כפר סבא"),
    (32.1852, 34.8991, "רח׳ הרצל, כפר סבא"),
    (32.1730, 34.8850, "רח׳ ירושלים, כפר סבא"),
    (32.1900, 34.9120, "רח׳ סוקולוב, כפר סבא"),
    (32.1815, 34.8780, "שד׳ רוטשילד, כפר סבא"),
    (32.1695, 34.8930, "רח׳ בן גוריון, כפר סבא"),
    (32.1940, 34.8850, "רח׳ התקווה, כפר סבא"),
    (32.1760, 34.9200, "רח׳ העצמאות, כפר סבא"),
    (32.1845, 34.8700, "שד׳ ויצמן, כפר סבא"),
    (32.1670, 34.9050, "רח׳ רש״י, כפר סבא"),
    (32.1920, 34.8780, "רח׳ דיזנגוף, כפר סבא"),
    (32.1800, 34.9300, "רח׳ הגפן, כפר סבא"),
    (32.1840, 34.8680, "רח׳ אלנבי, כפר סבא"),
    (32.1720, 34.8810, "רח׳ ז׳בוטינסקי, כפר סבא"),
    (32.1880, 34.9050, "מעבר חוצה שומרון"),
    # Ra'anana
    (32.1850, 34.8600, "רח׳ אחוזה, רעננה"),
    (32.1920, 34.8550, "שד׳ קרן קיימת, רעננה"),
    (32.1780, 34.8500, "רח׳ הרא״ה קוק, רעננה"),
    # Hod HaSharon
    (32.1550, 34.8900, "רח׳ שמשון, הוד השרון"),
    (32.1600, 34.8800, "רח׳ הבנים, הוד השרון"),
    (32.1480, 34.8950, "שד׳ רמתיים, הוד השרון"),
    # Herzliya
    (32.1650, 34.8450, "רח׳ הנשיא, הרצליה"),
    (32.1580, 34.8380, "שד׳ בן גוריון, הרצליה"),
    # Petah Tikva
    (32.0900, 34.8870, "רח׳ ביאליק, פתח תקווה"),
    (32.0850, 34.8780, "רח׳ סטמפר, פתח תקווה"),
    # Netanya
    (32.3230, 34.8560, "שד׳ בנימין, נתניה"),
    (32.3300, 34.8600, "רח׳ הרצל, נתניה"),
    (32.3180, 34.8520, "כיכר העצמאות, נתניה"),
    # More Kfar Saba spots
    (32.1830, 34.9000, "פארק נרדי, כפר סבא"),
    (32.1750, 34.8950, "בית ספר קפלן, כפר סבא"),
]

HAZARDS = [
    ("pothole", 0.06, 0.20, 0.15, 0.50, 0.10, 0.40),
    ("broken_sidewalk", 0.02, 0.08, 0.30, 1.20, 0.20, 0.80),
    ("crack", 0.01, 0.04, 0.50, 2.00, 0.01, 0.05),
    ("road_damage", 0.05, 0.15, 0.40, 1.50, 0.20, 0.90),
]

# Create a tiny black image for upload
import struct, zlib
def make_png(w, h, r, g, b):
    raw = b''
    for _ in range(h):
        raw += b'\x00' + bytes([r, g, b]) * w
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

print("🌱 Seeding CityInspect with demo data...\n")

for i, (lat, lon, address) in enumerate(LOCATIONS):
    hazard_type, d_min, d_max, w_min, w_max, a_min, a_max = random.choice(HAZARDS)

    # Randomize location slightly
    lat += random.uniform(-0.001, 0.001)
    lon += random.uniform(-0.001, 0.001)

    depth = round(random.uniform(d_min, d_max), 3)
    width = round(random.uniform(w_min, w_max), 3)
    length = round(random.uniform(w_min, w_max), 3)
    area = round(width * length, 4)

    # Make darker images for potholes
    brightness = random.randint(15, 45) if hazard_type == "pothole" else random.randint(50, 120)
    img = make_png(640, 480, brightness, brightness, brightness + random.randint(0, 10))

    lidar = {
        "depth_m": depth,
        "width_m": width,
        "length_m": length,
        "surface_area_m2": area,
    }

    files = {"image": ("incident.png", img, "image/png")}
    data = {
        "latitude": str(lat),
        "longitude": str(lon),
        "captured_at": f"2026-03-{random.randint(1,6):02d}T{random.randint(6,22):02d}:{random.randint(0,59):02d}:00Z",
        "lidar_measurements": str(lidar).replace("'", '"'),
        "device_info": '{"model":"iPhone 15 Pro","systemVersion":"17.4","lidarAvailable":"true"}',
    }

    try:
        resp = requests.post(f"{API}/incident/upload", headers=headers, files=files, data=data)
        if resp.ok:
            inc = resp.json()
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            print(f"  {sev_icon.get(inc['severity'], '⚪')} [{i+1:02d}/30] {inc['hazard_type']:18s} | {inc['severity']:8s} | AI {inc.get('ai_confidence', 0):.0%} | {address}")
        else:
            print(f"  ❌ [{i+1:02d}/30] Error: {resp.status_code} — {resp.text[:80]}")
    except Exception as e:
        print(f"  ❌ [{i+1:02d}/30] {e}")

    time.sleep(0.3)

print(f"\n✅ Done! Seeded {len(LOCATIONS)} incidents.")
print("🌐 Open the dashboard to see the data: file:///Users/$USER/CityInspect/cityinspect/dashboard-v3.html")
