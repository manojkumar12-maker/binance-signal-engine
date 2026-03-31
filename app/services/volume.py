from typing import List
import config


def check_volume_confirmation(oi_data: List[float]) -> bool:
    if len(oi_data) < 5:
        return True
    
    recent_oi = oi_data[-5:]
    avg_oi = sum(recent_oi) / len(recent_oi)
    
    if oi_data[-1] > avg_oi * 1.4:
        return True
    
    return False
