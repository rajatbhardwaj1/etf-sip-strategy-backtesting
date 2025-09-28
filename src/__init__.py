# src/__init__.py

from .backtester import Backtester
from .strategy import MovingAverageStrategy
from .utils import fetch_data

__all__ = ["Backtester", "MovingAverageStrategy", "fetch_data"]
