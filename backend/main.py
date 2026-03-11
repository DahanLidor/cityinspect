from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json, os
from database import engine, Base
from routes import auth, detections, tickets, work_orders

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CityInspect API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(detections.router)
app.include_router(tickets.router)
app.include_router(work_orders.router)

# ── WebSocket hub ──────────────────────────────────────
connected_clients: list[WebSocket] = []


async def broadcast(message: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0"}


@app.get("/")
def root():
    return {"message": "CityInspect API v2.0 — Urban Infrastructure Detection System"}
