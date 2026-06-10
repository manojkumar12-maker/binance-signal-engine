"""
SUPABASE INTEGRATION
===================

Purpose: Connect signal engine to Supabase database for:
- Storing signals
- Storing trades
- Real-time updates to frontend
- Analytics

Usage:
    from app.core.data.supabase_client import supabase
    
    # Save signal
    supabase.save_signal(signal_dict)
    
    # Get active signals
    signals = supabase.get_active_signals()
    
    # Save trade
    supabase.save_trade(trade_dict)
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import supabase
# If not installed, use mock implementation
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    create_client = None  # type: ignore
    logger.warning("Supabase client not installed. Using mock implementation.")


class SupabaseClient:
    """
    Supabase client for database operations.
    """
    
    def __init__(self, url: str = "", key: str = ""):
        self.url = url
        self.key = key
        self.client = None
        
        if SUPABASE_AVAILABLE and create_client and url and key:
            try:
                self.client = create_client(url, key)
                logger.info("✅ Supabase connected")
            except Exception as e:
                logger.error(f"❌ Supabase connection failed: {e}")
        else:
            logger.info("⚠️ Supabase not configured (using mock)")
    
    def save_signal(self, signal: Dict) -> bool:
        """
        Save signal to database.
        """
        if not self.client:
            logger.info("[MOCK] Saving signal")
            return True
        
        try:
            data = {
                "pair": signal.get("pair"),
                "signal": signal.get("signal"),
                "entry": signal.get("entry"),
                "sl": signal.get("sl"),
                "tp1": signal.get("tp1"),
                "tp2": signal.get("tp2"),
                "tp3": signal.get("tp3"),
                "confidence": signal.get("confidence"),
                "regime": signal.get("regime", {}).get("regime") if isinstance(signal.get("regime"), dict) else None,
                "tier": signal.get("tier"),
                "created_at": datetime.utcnow().isoformat(),
                "executed": False
            }
            
            self.client.table("signals").insert(data).execute()
            logger.info(f"✅ Signal saved: {signal.get('pair')}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save signal: {e}")
            return False
    
    def get_active_signals(self) -> List[Dict]:
        """
        Get active (non-executed) signals.
        """
        if not self.client:
            return []
        
        try:
            response = self.client.table("signals").select("*").eq("executed", False).order("created_at", desc=True).limit(10).execute()
            return response.data if response else []
        except Exception as e:
            logger.error(f"❌ Failed to get signals: {e}")
            return []
    
    def mark_signal_executed(self, signal_id: int) -> bool:
        """
        Mark signal as executed.
        """
        if not self.client:
            return True
        
        try:
            self.client.table("signals").update({"executed": True}).eq("id", signal_id).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update signal: {e}")
            return False
    
    def save_trade(self, trade: Dict) -> bool:
        """
        Save trade to database.
        """
        if not self.client:
            logger.info("[MOCK] Saving trade")
            return True
        
        try:
            data = {
                "pair": trade.get("pair"),
                "direction": trade.get("direction", trade.get("type")),
                "entry": trade.get("entry"),
                "exit": trade.get("exit"),
                "pnl": trade.get("pnl"),
                "status": trade.get("status", "OPEN"),
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.client.table("trades").insert(data).execute()
            logger.info(f"✅ Trade saved: {trade.get('pair')}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save trade: {e}")
            return False
    
    def get_trades(self, status: str = "") -> List[Dict]:
        """
        Get trades.
        """
        if not self.client:
            return []
        
        try:
            query = self.client.table("trades").select("*").order("created_at", desc=True)
            if status and status != "":
                query = query.eq("status", status)
            response = query.limit(50).execute()
            return response.data if response else []
        except Exception as e:
            logger.error(f"❌ Failed to get trades: {e}")
            return []
    
    def save_analytics(self, metric: str, value: float) -> bool:
        """
        Save analytics metric.
        """
        if not self.client:
            return True
        
        try:
            data = {
                "metric": metric,
                "value": value,
                "created_at": datetime.utcnow().isoformat()
            }
            self.client.table("analytics").insert(data).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save analytics: {e}")
            return False
    
    def get_analytics(self, metric: str = "") -> List[Dict]:
        """
        Get analytics data.
        """
        if not self.client:
            return []
        
        try:
            query = self.client.table("analytics").select("*").order("created_at", desc=True)
            if metric:
                query = query.eq("metric", metric)
            response = query.limit(100).execute()
            return response.data if response else []
        except Exception as e:
            logger.error(f"❌ Failed to get analytics: {e}")
            return []


# Global instance
_supabase = None

def get_supabase() -> SupabaseClient:
    global _supabase
    if _supabase is None:
        import os
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        _supabase = SupabaseClient(url, key)
    return _supabase


# Convenience functions
def save_signal(signal: Dict) -> bool:
    return get_supabase().save_signal(signal)

def get_active_signals() -> List[Dict]:
    return get_supabase().get_active_signals()

def save_trade(trade: Dict) -> bool:
    return get_supabase().save_trade(trade)

def get_trades(status: str = "") -> List[Dict]:
    return get_supabase().get_trades(status)
