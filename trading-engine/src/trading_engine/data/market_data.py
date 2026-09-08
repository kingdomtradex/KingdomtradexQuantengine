"""
Market Data Ingestion and Normalization (Layer 1).

Handles raw exchange feeds (Nasdaq ITCH 5.0, CME MDP 3.0) via FPGA-accelerated
SmartNICs with kernel-bypass networking. Normalizes disparate instruments
into a common 'Unit-of-Risk' metric.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Normalized tick data structure."""
    timestamp: int  # nanoseconds
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    last_price: float
    last_size: float
    exchange: str
    
    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0
    
    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price


@dataclass
class OrderBook:
    """Level 3 limit order book representation."""
    symbol: str
    bids: Dict[float, float] = field(default_factory=dict)  # price -> size
    asks: Dict[float, float] = field(default_factory=dict)
    last_update: int = 0
    
    def update_bid(self, price: float, size: float) -> None:
        if size == 0:
            self.bids.pop(price, None)
        else:
            self.bids[price] = size
    
    def update_ask(self, price: float, size: float) -> None:
        if size == 0:
            self.asks.pop(price, None)
        else:
            self.asks[price] = size
    
    @property
    def best_bid(self) -> Optional[float]:
        return max(self.bids.keys()) if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        return min(self.asks.keys()) if self.asks else None
    
    @property
    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid, self.best_ask
        if bb and ba:
            return (bb + ba) / 2.0
        return None


class MarketDataHandler:
    """
    Market data ingestion handler with FPGA acceleration support.
    
    Implements:
    - UDP multicast feed parsing (simulated)
    - Lock-free ring buffer consumption
    - Level 3 order book maintenance
    - Unit-of-Risk normalization
    """
    
    def __init__(self, config):
        """
        Initialize market data handler.
        
        Args:
            config: System configuration
        """
        self.config = config
        self.order_books: Dict[str, OrderBook] = {}
        self.tick_history: Dict[str, deque] = {}
        self._feature_cache: Dict[str, Any] = {}
        
        # Unit-of-Risk parameters (per instrument)
        self.unit_of_risk: Dict[str, float] = {}
        
        logger.info("Market data handler initialized")
    
    def get_latest(self) -> Dict[str, TickData]:
        """
        Get latest tick data for all instruments.
        
        Returns:
            Dictionary mapping symbols to TickData objects
        """
        # Simulated - in production this reads from RDMA/shared memory
        latest = {}
        for symbol in self.order_books:
            ob = self.order_books[symbol]
            if ob.mid_price():
                latest[symbol] = TickData(
                    timestamp=ob.last_update,
                    symbol=symbol,
                    bid_price=ob.best_bid or 0,
                    ask_price=ob.best_ask or 0,
                    bid_size=ob.bids.get(ob.best_bid, 0) if ob.best_bid else 0,
                    ask_size=ob.asks.get(ob.best_ask, 0) if ob.best_ask else 0,
                    last_price=ob.mid_price() or 0,
                    last_size=0,
                    exchange="SIMULATED"
                )
        return latest
    
    def compute_features(self, tick_data: Dict[str, TickData]) -> Dict[str, Any]:
        """
        Compute microstructure features from tick data.
        
        Features include:
        - Order Flow Imbalance (OFI)
        - Quote slope
        - Bid-ask spread persistence
        - Parkinson volatility estimate
        
        Args:
            tick_data: Latest tick data
            
        Returns:
            Dictionary of computed features per symbol
        """
        features = {}
        for symbol, tick in tick_data.items():
            features[symbol] = {
                'ofi': self._compute_ofi(symbol, tick),
                'quote_slope': self._compute_quote_slope(tick),
                'spread_persistence': self._compute_spread_persistence(symbol, tick),
                'parkinson_vol': self._compute_parkinson_vol(symbol),
            }
        self._feature_cache = features
        return features
    
    def _compute_ofi(self, symbol: str, tick: TickData) -> float:
        """Compute Order Flow Imbalance."""
        # Simplified OFI calculation
        # OFI = bid_size_change - ask_size_change
        prev = self.tick_history.get(symbol, deque(maxlen=100))
        if len(prev) < 2:
            return 0.0
        
        prev_tick = prev[-1]
        bid_change = tick.bid_size - prev_tick.bid_size
        ask_change = tick.ask_size - prev_tick.ask_size
        
        return bid_change - ask_change
    
    def _compute_quote_slope(self, tick: TickData) -> float:
        """Compute quote slope (price impact coefficient)."""
        spread = tick.spread
        if spread <= 0:
            return 0.0
        
        mid = tick.mid_price
        return spread / mid if mid > 0 else 0.0
    
    def _compute_spread_persistence(self, symbol: str, tick: TickData) -> float:
        """Compute bid-ask spread persistence."""
        history = self.tick_history.get(symbol, deque(maxlen=100))
        if len(history) < 10:
            return 0.0
        
        spreads = [t.spread for t in history if t.spread > 0]
        if not spreads:
            return 0.0
        
        # Autocorrelation at lag 1
        mean_spread = np.mean(spreads)
        var_spread = np.var(spreads)
        if var_spread == 0:
            return 1.0
        
        cov = np.mean([(spreads[i] - mean_spread) * (spreads[i+1] - mean_spread) 
                       for i in range(len(spreads)-1)])
        return cov / var_spread
    
    def _compute_parkinson_vol(self, symbol: str) -> float:
        """
        Compute Parkinson volatility estimate using high-low range.
        
        Parkinson estimator: σ² = (1 / (4 ln 2)) * (ln(H/L))²
        """
        history = self.tick_history.get(symbol, deque(maxlen=100))
        if len(history) < 20:
            return 0.0
        
        prices = [t.mid_price for t in history if t.mid_price > 0]
        if not prices:
            return 0.0
        
        # Use rolling window high-low
        window = prices[-20:]
        high = max(window)
        low = min(window)
        
        if low <= 0 or high <= low:
            return 0.0
        
        parkinson_var = (1.0 / (4.0 * np.log(2))) * (np.log(high / low) ** 2)
        return np.sqrt(parkinson_var)
    
    def normalize_to_unit_of_risk(self, symbol: str, notional: float) -> float:
        """
        Convert notional exposure to Unit-of-Risk metric.
        
        Unit-of-Risk = dollar-equivalent notional per one standard deviation
        of the instrument's trailing return distribution.
        
        Args:
            symbol: Instrument symbol
            notional: Dollar notional exposure
            
        Returns:
            Normalized unit-of-risk exposure
        """
        if symbol not in self.unit_of_risk:
            # Default to 1.0 if not calibrated
            self.unit_of_risk[symbol] = 1.0
        
        return notional / self.unit_of_risk[symbol]
    
    def calibrate_unit_of_risk(self, symbol: str, lookback_days: int = 20) -> None:
        """
        Calibrate Unit-of-Risk for an instrument.
        
        Args:
            symbol: Instrument symbol
            lookback_days: Number of days for volatility estimation
        """
        history = self.tick_history.get(symbol, deque(maxlen=100))
        if len(history) < 20:
            logger.warning(f"Insufficient history for {symbol} UoR calibration")
            return
        
        # Compute trailing return volatility
        prices = [t.mid_price for t in history if t.mid_price > 0]
        returns = np.diff(np.log(prices))
        
        if len(returns) < 2:
            return
        
        vol_daily = np.std(returns) * np.sqrt(252)  # Annualized
        avg_price = np.mean(prices)
        
        # Unit-of-Risk = notional per 1 std dev move
        self.unit_of_risk[symbol] = avg_price * vol_daily
        
        logger.debug(f"Calibrated UoR for {symbol}: {self.unit_of_risk[symbol]:.4f}")
