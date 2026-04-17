from typing import List, Dict


def build_4h(candles_1h: List[Dict]) -> List[Dict]:
    if not candles_1h or len(candles_1h) < 4:
        return []
    
    candles_4h = []
    
    for i in range(0, len(candles_1h), 4):
        chunk = candles_1h[i:i+4]
        if len(chunk) < 4:
            continue
        
        candles_4h.append({
            "open": chunk[0]['open'],
            "high": max(c['high'] for c in chunk),
            "low": min(c['low'] for c in chunk),
            "close": chunk[-1]['close'],
            "volume": sum(c.get('volume', 0) for c in chunk)
        })
    
    return candles_4h


def build_15m(candles_1h: List[Dict]) -> List[Dict]:
    if not candles_1h or len(candles_1h) < 1:
        return []
    
    candles_15m = []
    
    for i in range(0, len(candles_1h), 1):
        chunk = candles_1h[i:i+1]
        if not chunk:
            continue
        candles_15m.extend(chunk)
    
    return candles_15m


def get_latest_candle(candles: List[Dict]) -> Dict:
    return candles[-1] if candles else {}


def get_closed_candles(candles: List[Dict]) -> List[Dict]:
    return [c for c in candles if c.get('closed', False)]
