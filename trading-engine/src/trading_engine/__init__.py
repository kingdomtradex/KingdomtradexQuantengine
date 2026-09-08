"""
Trading Engine - Statistical Arbitrage and Market-Making System

A low-latency, multi-agent ensemble trading system for cross-asset
statistical arbitrage and market-making.
"""

from .engine import TradingEngine
from .config import Config

__version__ = "2.2.0"
__author__ = "Quantitative Research Department"
__all__ = ["TradingEngine", "Config"]
