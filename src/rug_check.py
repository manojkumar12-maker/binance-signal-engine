"""Asset and market risk assessment for Binance Futures symbols."""
from decimal import Decimal
from typing import Optional


class RugChecker:
    def assess(self, symbol: str, klines: list) -> dict:
        reasons = []
        warnings = []
        metrics = {}
        if not klines or len(klines) < 20:
            return {
                "symbol": symbol,
                "risk_rating": "UNKNOWN",
                "reasons": ["Insufficient market history"],
                "warnings": ["Missing or limited data; not treated as safe"],
                "metrics": {"candles": len(klines) if klines else 0},
            }

        closes = [Decimal(str(k[4])) for k in klines]
        highs = [Decimal(str(k[2])) for k in klines]
        lows = [Decimal(str(k[3])) for k in klines]
        volumes = [Decimal(str(k[5])) for k in klines]

        # ATR %
        from . import indicators as ind
        atr_val = ind.atr(highs, lows, closes, 14)
        last_close = closes[-1]
        atr_pct = (atr_val / last_close * Decimal(100)) if (atr_val and last_close) else None
        metrics["atr"] = str(atr_val) if atr_val else None
        metrics["atr_percent"] = str(atr_pct) if atr_pct else None

        avg_vol = sum(volumes[-21:-1]) / Decimal(20) if len(volumes) >= 21 else None
        last_vol = volumes[-1]
        vol_ratio = (last_vol / avg_vol) if (avg_vol and avg_vol > 0) else None
        metrics["volume_ratio"] = str(vol_ratio) if vol_ratio else None

        rating = "LOW"
        # Extreme volatility
        if atr_pct is not None and atr_pct > Decimal("5"):
            rating = "HIGH"
            reasons.append(f"Extreme volatility: ATR {atr_pct:.2f}% of price")
        elif atr_pct is not None and atr_pct > Decimal("3"):
            if rating == "LOW":
                rating = "MEDIUM"
            reasons.append(f"Elevated volatility: ATR {atr_pct:.2f}%")

        # Abnormal volume spike
        if vol_ratio is not None and vol_ratio > Decimal("5"):
            rating = "HIGH"
            reasons.append(f"Abnormal volume spike: {vol_ratio:.2f}x average")
        elif vol_ratio is not None and vol_ratio > Decimal("3"):
            if rating == "LOW":
                rating = "MEDIUM"
            reasons.append(f"Unusual volume: {vol_ratio:.2f}x average")

        # Low liquidity (low average volume)
        if avg_vol is not None and avg_vol < Decimal("10"):
            if rating == "LOW":
                rating = "MEDIUM"
            warnings.append("Low average volume; liquidity may be limited")

        # Missing data warning
        if len(klines) < 50:
            if rating == "LOW":
                rating = "MEDIUM"
            warnings.append("Limited historical data")

        if not reasons:
            reasons.append("No abnormal market-risk signals detected in available data")
        if not warnings:
            warnings.append("Assessment based only on available exchange market data")

        metrics["candles"] = len(klines)
        metrics["last_close"] = str(last_close)
        return {
            "symbol": symbol,
            "risk_rating": rating,
            "reasons": reasons,
            "warnings": warnings,
            "metrics": metrics,
        }