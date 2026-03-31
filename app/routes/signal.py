from fastapi import APIRouter, Query
from app.services.strategy import generate_signal

router = APIRouter()


@router.get("/signal/{pair}")
def get_signal(
    pair: str,
    timeframe: str = Query("1h", regex="^(15m|1h|4h)$")
):
    return generate_signal(pair.upper(), timeframe)


@router.get("/pairs")
def get_pairs():
    return {
        "pairs": [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"
        ]
    }
