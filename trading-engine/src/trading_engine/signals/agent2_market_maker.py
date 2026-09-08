"""
Agent 2: Market-Making Agent.

Implements Avellaneda-Stoikov framework for passive liquidity provision.
Dynamically skews quotes based on inventory and directional conviction.
"""

import logging
import numpy as np
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MarketMakingAgent:
    """
    Avellaneda-Stoikov market-making agent.
    
    Reservation price: r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
    """
    
    def __init__(self, config):
        self.config = config
        self.gamma = 0.1  # Risk aversion parameter
        self.inventory: Dict[str, float] = {}
        logger.info("Market-making agent initialized")
    
    def generate_signal(
        self, 
        market_data: Dict[str, Any], 
        features: Dict[str, Any],
        regime_state: int
    ) -> Dict[str, Any]:
        """Generate market-making signals using Avellaneda-Stoikov."""
        positions = {}
        
        # Reduce activity in high-vol regimes
        if regime_state >= 1:
            scale = 0.5 if regime_state == 1 else 0.0
        else:
            scale = 1.0
        
        for symbol, tick in market_data.items():
            if symbol not in features:
                continue
            
            mid = tick.mid_price if hasattr(tick, 'mid_price') else 0
            if mid <= 0:
                continue
            
            # Get volatility estimate
            vol = features[symbol].get('parkinson_vol', 0.02)
            
            # Current inventory
            inv = self.inventory.get(symbol, 0.0)
            
            # Avellaneda-Stoikov reservation price
            # Assuming T-t = 1 (continuous quoting)
            reservation = mid - inv * self.gamma * (vol ** 2)
            
            # Skew based on order flow imbalance
            ofi = features[symbol].get('ofi', 0.0)
            reservation += 0.0001 * ofi  # Small OFI adjustment
            
            # Generate quote skew signal
            if reservation > mid * 1.0001:
                positions[symbol] = 1.0 * scale  # Bid skew
            elif reservation < mid * 0.9999:
                positions[symbol] = -1.0 * scale  # Ask skew
            
            # Update inventory (simplified)
            self.inventory[symbol] = inv + 0.01 * positions.get(symbol, 0)
        
        return {
            'positions': positions,
            'pnl_estimate': 0.0005,
            'vol_estimate': 0.015,
        }
