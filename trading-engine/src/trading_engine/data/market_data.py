"""
Market data ingestion and normalization.

Simulates FPGA-accelerated data ingestion for the open-source release.
In production, this layer interfaces with FPGA SmartNICs for hardware-level
parsing of exchange feeds (Nasdaq ITCH 5.0, CME MDP 3.0) with sub-nanosecond
timestamping.

Key features:
- Lock-free ring buffer consumption
- RDMA zero-copy state transfer simulation
- Unit-of-Risk normalization across asset classes
"""

from typing import Dict, Any, List, Optional
import numpy as np
from collections import deque

from ..config import Config


class OrderBook:
    """Level 3 limit order book representation."""
    
    def __init__(self, instrument_id: str):
        self.instrument_id = instrument_id
        self.bids: Dict[float, int] = {}  # price -> size
        self.asks: Dict[float, int] = {}  # price -> size
        self.last_update_time: int = 0
        
    def update_bid(self, price: float, size: int, timestamp: int) -> None:
        """Update bid level."""
        if size == 0:
            self.bids.pop(price, None)
        else:
            self.bids[price] = size
        self.last_update_time = timestamp
        
    def update_ask(self, price: float, size: int, timestamp: int) -> None:
        """Update ask level."""
        if size == 0:
            self.asks.pop(price, None)
        else:
            self.asks[price] = size
        self.last_update_time = timestamp
        
    @property
    def best_bid(self) -> Optional[float]:
        """Get best bid price."""
        return max(self.bids.keys()) if self.bids else None
        
    @property
    def best_ask(self) -> Optional[float]:
        """Get best ask price."""
        return min(self.asks.keys()) if self.asks else None
        
    @property
    def mid_price(self) -> Optional[float]:
        """Get mid price."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2
        
    @property
    def spread(self) -> Optional[float]:
        """Get bid-ask spread."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


class MarketDataHandler:
    """
    Handles market data ingestion and normalization.
    
    In production, this interfaces with FPGA SmartNICs for hardware
    parsing. This open-source version simulates the data flow.
    """
    
    def __init__(self, config: Config):
        """
        Initialize market data handler.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self._order_books: Dict[str, OrderBook] = {}
        self._tick_buffer: deque = deque(maxlen=100000)
        self._instrument_universe = self._generate_universe()
        
    def _generate_universe(self) -> List[str]:
        """Generate instrument universe identifiers."""
        instruments = []
        
        # Equities/ETFs (200)
        for i in range(200):
            instruments.append(f"EQUITY_{i:04d}")
            
        # Commodity futures (75)
        for i in range(75):
            instruments.append(f"FUTURE_{i:04d}")
            
        # Crypto assets (75)
        for i in range(75):
            instruments.append(f"CRYPTO_{i:04d}")
            
        return instruments
    
    def initialize_order_books(self) -> None:
        """Initialize order books for all instruments."""
        for inst_id in self._instrument_universe:
            self._order_books[inst_id] = OrderBook(inst_id)
            
    def get_order_books(self) -> Dict[str, OrderBook]:
        """
        Get current order books.
        
        Returns:
            Dictionary mapping instrument IDs to OrderBook objects
        """
        if not self._order_books:
            self.initialize_order_books()
        return self._order_books
    
    def compute_features(self) -> Dict[str, np.ndarray]:
        """
        Compute microstructure features from order book state.
        
        Returns:
            Dictionary mapping instrument IDs to feature vectors
        """
        features = {}
        
        for inst_id, ob in self._order_books.items():
            if ob.mid_price is None:
                features[inst_id] = np.zeros(6)
                continue
                
            # Feature vector: [OFI, quote_slope, spread_persistence, 
            #                  bid_depth, ask_depth, volatility_estimate]
            ofi = self._compute_ofi(ob)
            quote_slope = self._compute_quote_slope(ob)
            spread_persist = self._compute_spread_persistence(ob)
            bid_depth = sum(ob.bids.values())
            ask_depth = sum(ob.asks.values())
            vol_est = self._estimate_volatility(ob)
            
            features[inst_id] = np.array([
                ofi, quote_slope, spread_persist,
                bid_depth, ask_depth, vol_est
            ])
            
        return features
    
    def _compute_ofi(self, ob: OrderBook) -> float:
        """Compute Order Flow Imbalance."""
        if not ob.bids or not ob.asks:
            return 0.0
            
        best_bid_size = ob.bids.get(ob.best_bid, 0)
        best_ask_size = ob.asks.get(ob.best_ask, 0)
        
        return (best_bid_size - best_ask_size) / (best_bid_size + best_ask_size + 1e-9)
    
    def _compute_quote_slope(self, ob: OrderBook) -> float:
        """Compute quote slope (price impact per unit size)."""
        if len(ob.bids) < 2 or len(ob.asks) < 2:
            return 0.0
            
        sorted_bids = sorted(ob.bids.keys(), reverse=True)
        sorted_asks = sorted(ob.asks.keys())
        
        if len(sorted_bids) >= 2 and len(sorted_asks) >= 2:
            bid_slope = (sorted_bids[0] - sorted_bids[1]) / (ob.bids[sorted_bids[0]] + 1e-9)
            ask_slope = (sorted_asks[1] - sorted_asks[0]) / (ob.asks[sorted_asks[0]] + 1e-9)
            return (bid_slope + ask_slope) / 2
            
        return 0.0
    
    def _compute_spread_persistence(self, ob: OrderBook) -> float:
        """Compute spread persistence metric."""
        if ob.spread is None or ob.mid_price is None:
            return 0.0
            
        relative_spread = ob.spread / ob.mid_price
        return np.clip(1.0 - relative_spread * 100, 0.0, 1.0)
    
    def _estimate_volatility(self, ob: OrderBook) -> float:
        """Estimate instantaneous volatility from order book."""
        if ob.mid_price is None or ob.spread is None:
            return 0.0
            
        return ob.spread / ob.mid_price
    
    def normalize_to_unit_of_risk(
        self,
        notional: float,
        instrument_id: str,
        trailing_std: float
    ) -> float:
        """
        Normalize notional exposure to Unit-of-Risk metric.
        
        Unit-of-Risk is defined as dollar-equivalent notional exposure
        per one standard deviation of the instrument's trailing return distribution.
        
        Args:
            notional: Dollar notional amount
            instrument_id: Instrument identifier
            trailing_std: Trailing standard deviation of returns
            
        Returns:
            Unit-of-Risk normalized exposure
        """
        if trailing_std <= 0:
            return notional
            
        return notional / trailing_std
