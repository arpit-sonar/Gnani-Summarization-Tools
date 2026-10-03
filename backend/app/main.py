import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import recordings
from app.worker import main as start_worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_thread = threading.Thread(target=start_worker_loop, daemon=True)
    worker_thread.start()
    print("Background worker thread started inside Web Service")
    yield


app = FastAPI(title="Gnani Summarization Tools API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recordings.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}