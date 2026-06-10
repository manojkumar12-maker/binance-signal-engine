"""
PHASE 5: VOLUME PROFILE ENGINE
==============================

PURPOSE:
Calculate Volume Profile, Point of Control (POC), Value Area High (VAH),
Value Area Low (VAL) for support/resistance zones.

FORMULAS:
1. Volume Profile: Histogram of volume at price levels
2. POC: Price level with highest volume
3. Value Area: 70% of total volume
4. VAH: Highest price in value area
5. VAL: Lowest price in value area

USAGE:
- Entry near VAL = discount (longs)
- Entry near VAH = premium (shorts)
- POC = strongest support/resistance
- Break above VAH = bullish continuation
- Break below VAL = bearish continuation

THRESHOLDS:
- Price within 2% of VAL = discount zone
- Price within 2% of VAH = premium zone
- Price within 1% of POC = key level
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class VolumeProfileResult:
    poc: float
    vah: float
    val: float
    value_area_width: float
    volume_score: float
    price_location: str
    nearest_level: str
    level_distance: float
    
    def to_dict(self) -> Dict:
        return {
            "poc": round(self.poc, 4),
            "vah": round(self.vah, 4),
            "val": round(self.val, 4),
            "value_area_width": round(self.value_area_width, 4),
            "volume_score": round(self.volume_score, 2),
            "price_location": self.price_location,
            "nearest_level": self.nearest_level,
            "level_distance": round(self.level_distance, 4)
        }


class VolumeProfile:
    """
    Calculate Volume Profile from candle data.
    """
    
    def __init__(self, bins: int = 50):
        self.bins = bins
    
    def calculate(self, candles: List[Dict]) -> VolumeProfileResult:
        if len(candles) < 20:
            return VolumeProfileResult(
                poc=0, vah=0, val=0, value_area_width=0,
                volume_score=0, price_location="UNKNOWN",
                nearest_level="NONE", level_distance=0
            )
        
        # Extract price and volume
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        volumes = np.array([c.get("volume", 0) for c in candles])
        
        current_price = candles[-1]["close"]
        
        # Calculate profile
        profile, bin_edges = self._calculate_profile(lows, highs, volumes)
        
        # Find POC
        poc_idx = np.argmax(profile)
        poc = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2
        
        # Calculate Value Area
        vah, val = self._calculate_value_area(profile, bin_edges, volumes)
        
        # Determine price location
        location, nearest_level, distance = self._locate_price(
            current_price, poc, vah, val
        )
        
        # Calculate volume score
        volume_score = self._calculate_volume_score(candles)
        
        return VolumeProfileResult(
            poc=poc,
            vah=vah,
            val=val,
            value_area_width=vah - val,
            volume_score=volume_score,
            price_location=location,
            nearest_level=nearest_level,
            level_distance=distance
        )
    
    def _calculate_profile(self, lows: np.ndarray, highs: np.ndarray,
                           volumes: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate volume profile histogram."""
        
        min_price = np.min(lows)
        max_price = np.max(highs)
        
        if max_price <= min_price:
            return np.zeros(self.bins), np.linspace(min_price, min_price + 1, self.bins + 1)
        
        bin_edges = np.linspace(min_price, max_price, self.bins + 1)
        profile = np.zeros(self.bins)
        
        for i in range(len(lows)):
            low_bin = np.searchsorted(bin_edges, lows[i]) - 1
            high_bin = np.searchsorted(bin_edges, highs[i]) - 1
            
            low_bin = max(0, low_bin)
            high_bin = min(self.bins - 1, high_bin)
            
            if low_bin == high_bin:
                profile[low_bin] += volumes[i]
            else:
                # Distribute volume across bins
                bins_count = high_bin - low_bin + 1
                vol_per_bin = volumes[i] / bins_count
                for j in range(low_bin, high_bin + 1):
                    profile[j] += vol_per_bin
        
        return profile, bin_edges
    
    def _calculate_value_area(self, profile: np.ndarray, bin_edges: np.ndarray,
                               volumes: np.ndarray) -> Tuple[float, float]:
        """Calculate Value Area (70% of volume)."""
        
        total_volume = np.sum(profile)
        target_volume = total_volume * 0.70
        
        # Find POC
        poc_idx = np.argmax(profile)
        
        # Expand outward from POC
        vah_idx = poc_idx
        val_idx = poc_idx
        current_volume = profile[poc_idx]
        
        while current_volume < target_volume:
            added = False
            
            # Try to add higher bin
            if vah_idx < len(profile) - 1:
                if vah_idx + 1 < len(profile):
                    current_volume += profile[vah_idx + 1]
                    vah_idx += 1
                    added = True
            
            # Try to add lower bin
            if val_idx > 0:
                if val_idx - 1 >= 0:
                    current_volume += profile[val_idx - 1]
                    val_idx -= 1
                    added = True
            
            if not added:
                break
        
        vah = bin_edges[vah_idx + 1]
        val = bin_edges[val_idx]
        
        return vah, val
    
    def _locate_price(self, price: float, poc: float, vah: float, val: float) -> Tuple[str, str, float]:
        """Determine where price is relative to profile levels."""
        
        if price > vah:
            distance = (price - vah) / (vah - val) if (vah - val) > 0 else 0
            return "ABOVE_VA", "VAH", distance
        
        if price < val:
            distance = (val - price) / (vah - val) if (vah - val) > 0 else 0
            return "BELOW_VAL", "VAL", distance
        
        # Within value area
        if abs(price - poc) / poc < 0.01:
            return "AT_POC", "POC", 0
        
        if price > poc:
            distance = (price - poc) / (vah - poc) if (vah - poc) > 0 else 0
            return "ABOVE_POC", "POC", distance
        else:
            distance = (poc - price) / (poc - val) if (poc - val) > 0 else 0
            return "BELOW_POC", "POC", distance
    
    def _calculate_volume_score(self, candles: List[Dict]) -> float:
        """Score volume health."""
        volumes = np.array([c.get("volume", 0) for c in candles[-20:]])
        
        if len(volumes) < 2:
            return 50.0
        
        mean = np.mean(volumes[:-1])
        last = volumes[-1]
        
        if mean == 0:
            return 50.0
        
        ratio = last / mean
        
        # Score: higher volume = higher score (up to 100)
        score = min(100, ratio * 50)
        
        return float(score)
    
    def get_support_resistance(self, result: VolumeProfileResult) -> Dict:
        """Get support/resistance levels from volume profile."""
        return {
            "support": result.val,
            "resistance": result.vah,
            "poc": result.poc,
            "strong_support": result.val,
            "strong_resistance": result.vah
        }


# Global instance
_volume_profile = None

def get_profile() -> VolumeProfile:
    global _volume_profile
    if _volume_profile is None:
        _volume_profile = VolumeProfile()
    return _volume_profile


def calculate_volume_profile(candles: List[Dict]) -> Dict:
    profile = get_profile()
    return profile.calculate(candles).to_dict()
