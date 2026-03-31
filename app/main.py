from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.signal import router as signal_router

app = FastAPI(title="Binance Signal Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signal_router, prefix="/api", tags=["signals"])


@app.get("/")
def root():
    return {"status": "online", "app": "Binance Signal Engine"}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
