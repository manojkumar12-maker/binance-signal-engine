from typing import Optional


def calculate_confidence(trend: str, liquidity: Optional[str], volume: bool) -> int:
    score = 0
    
    if trend != "RANGE":
        score += 30
    
    if liquidity is not None:
        score += 30
    
    if volume:
        score += 40
    
    return score
