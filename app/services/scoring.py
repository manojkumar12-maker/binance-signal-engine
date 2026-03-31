from typing import Optional


def calculate_confidence(trend: str, liquidity: Optional[str], volume: bool, strength: int = 0) -> int:
    score = 0
    
    if trend != "RANGE":
        score += 25
    
    if liquidity is not None:
        score += 25
    
    if volume:
        score += 30
    
    score += min(strength, 20)
    
    return min(score, 100)
