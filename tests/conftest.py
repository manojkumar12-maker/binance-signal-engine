import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("TRADING_MODE", "paper")

import pytest
from decimal import Decimal

from src.config import Settings