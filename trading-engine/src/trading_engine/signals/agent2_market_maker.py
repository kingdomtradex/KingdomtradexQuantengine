"""
Agent 2: Market-Making Agent.

Implements the Avellaneda-Stoikov framework for optimal market-making
with dynamic quote skewing based on inventory and directional conviction.

Reference:
Avellaneda, M., & Stoikov, S. (2008). High-Frequency Trading in a Limit Order Book.
Quantitative Finance.
"""

from typing import Dict, Any, Optional
import numpy as np

from ..config import Config


class MarketMakingAgent:
    """
    Avellaneda-Stoikov market-making agent.
    
    Computes optimal bid/ask quotes based on:
    - Current mid-price
    - Inventory position
    - Risk aversion parameter
    - Volatility estimate
    - Time horizon
    """
    
    def __init__(self, config: Config):
        """
        Initialize market-making agent.
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Avellaneda-Stoikov parameters
        self.gamma = 0.1  # Risk aversion parameter
        self.T = 1.0  # Time horizon (seconds)
        
        # Inventory tracking
        self._inventory: Dict[str, float] = {}
        self._avg_entry: Dict[str, float] = {}
        
    def generate_signal(
        self,
        instrument_id: str,
        state: Any
    ) -> float:
        """
        Generate market-making signal.
        
        Args:
            instrument_id: Instrument identifier
            state: Current market state
            
        Returns:
            Signal value representing desired inventory change
        """
        ob = state.order_books.get(instrument_id)
        
        if ob is None or ob.mid_price is None:
            return 0.0
            
        # Get current inventory
        inventory = self._inventory.get(instrument_id, 0.0)
        
        # Calculate reservation price using Avellaneda-Stoikov formula
        r = self._reservation_price(
            s=ob.mid_price,
            q=inventory,
            sigma=state.features[instrument_id][5] if instrument_id in state.features else 0.01,
            t=0.5  # Assume halfway through horizon
        )
        
        # Calculate optimal spread
        spread = self._optimal_spread(
            sigma=state.features[instrument_id][5] if instrument_id in state.features else 0.01,
            gamma=self.gamma
        )
        
        # Determine quoting strategy
        # If reservation price > mid, we want to buy (positive signal)
        # If reservation price < mid, we want to sell (negative signal)
        signal = (r - ob.mid_price) / (ob.mid_price + 1e-9)
        
        # Scale by spread for confidence
        signal *= spread * 100
        
        return float(np.clip(signal, -1.0, 1.0))
    
    def _reservation_price(
        self,
        s: float,
        q: float,
        sigma: float,
        t: float
    ) -> float:
        """
        Calculate reservation price per Avellaneda-Stoikov.
        
        r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
        
        Args:
            s: Current mid-price
            q: Current inventory
            sigma: Volatility (standard deviation of returns)
            t: Current time (fraction of horizon)
            
        Returns:
            Reservation price
        """
        return s - q * self.gamma * (sigma ** 2) * (self.T - t)
    
    def _optimal_spread(
        self,
        sigma: float,
        gamma: float
    ) -> float:
        """
        Calculate optimal spread.
        
        Args:
            sigma: Volatility
            gamma: Risk aversion
            
        Returns:
            Optimal half-spread
        """
        # Simplified: optimal spread proportional to volatility and risk aversion
        return gamma * (sigma ** 2) * self.T
    
    def update_inventory(
        self,
        instrument_id: str,
        quantity: float,
        price: float
    ) -> None:
        """
        Update inventory after fill.
        
        Args:
            instrument_id: Instrument identifier
            quantity: Trade quantity (positive=buy, negative=sell)
            price: Fill price
        """
        if instrument_id not in self._inventory:
            self._inventory[instrument_id] = 0.0
            self._avg_entry[instrument_id] = 0.0
            
        old_qty = self._inventory[instrument_id]
        old_avg = self._avg_entry[instrument_id]
        
        new_qty = old_qty + quantity
        
        if new_qty != 0:
            # Update average entry price
            if old_qty * quantity >= 0:  # Adding to position
                self._avg_entry[instrument_id] = (
                    (old_qty * old_avg + quantity * price) / new_qty
                )
            else:  # Reducing position
                self._avg_entry[instrument_id] = old_avg
                
        self._inventory[instrument_id] = new_qty
        
        if abs(new_qty) < 1e-6:
            self._inventory[instrument_id] = 0.0
            self._avg_entry[instrument_id] = 0.0
    
    def get_inventory(self, instrument_id: str) -> float:
        """Get current inventory for instrument."""
        return self._inventory.get(instrument_id, 0.0)
    
    def skew_quotes(
        self,
        bid_price: float,
        ask_price: float,
        inventory: float,
        directional_conviction: float
    ) -> tuple:
        """
        Skew quotes based on inventory and directional view.
        
        Args:
            bid_price: Raw bid price
            ask_price: Raw ask price
            inventory: Current inventory
            directional_conviction: Signal from other agents (-1 to 1)
            
        Returns:
            Tuple of (skewed_bid, skewed_ask)
        """
        # Inventory skew: reduce exposure when heavily positioned
        inventory_skew = inventory * self.gamma * 0.001
        
        # Directional skew: lean into conviction
        directional_skew = directional_conviction * 0.002
        
        total_skew = inventory_skew + directional_skew
        
        return (bid_price - total_skew, ask_price - total_skew)
