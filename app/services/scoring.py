from typing import Optional


def calculate_confidence(trend: str, liquidity: Optional[str], volume: bool, strength: int = 0, volume_spike: bool = False) -> int:
    score = 0
    
    if trend != "RANGE":
        score += 25
    
    if liquidity is not None:
        if "REJECTION" in liquidity:
            score += 25
        else:
            score += 15
    
    if volume_spike:
        score += 20
    elif volume:
        score += 5
    
    score += min(strength, 20)
    
    return min(score, 100)
