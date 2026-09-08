"""
Agent 4: Volatility Risk Premium Scaler.

Multiplicative exposure scaler based on the variance risk premium (VRP).

This agent enables the aggressive leverage regime by scaling gross exposure
toward the 10.0x ceiling when IV > RV (positive variance risk premium) and
forcing de-leveraging when RV > IV (premium inversion).

Reference:
Carr, P., & Wu, L. (2009). Variance Risk Premiums. Review of Financial Studies.
"""

from typing import Dict, Any, Optional
import numpy as np

from ..config import Config


class VolatilityRiskScaler:
    """
    Volatility risk premium exposure scaler.
    
    Computes VRP = IV^2 - RV^2 and scales leverage accordingly:
    - Positive VRP (IV > RV): Scale toward max leverage
    - Negative VRP (RV > IV): De-lever to base
    
    This is NOT an independent directional signal but a multiplicative
    scaler on the aggregate output of Agents 1-3.
    """
    
    def __init__(self, config: Config):
        """
        Initialize volatility risk scaler.
        
        Args:
            config: Configuration object with leverage parameters
        """
        self.config = config
        
        # Leverage parameters
        self.max_leverage = config.leverage.max_leverage
        self.base_leverage = config.leverage.base_leverage
        self.vrp_sensitivity = config.leverage.vrp_sensitivity
        
        # VRP tracking
        self._iv_history: list = []
        self._rv_history: list = []
        self._vrp_history: list = []
        
        # Volatility estimation windows
        self.rv_window = 20  # Days for realized vol
        self.iv_source = "VIX"  # Implied vol source
        
    def generate_signal(
        self,
        instrument_id: str,
        state: Any
    ) -> float:
        """
        Generate VRP-based leverage multiplier signal.
        
        Args:
            instrument_id: Instrument identifier
            state: Current market state
            
        Returns:
            Leverage multiplier (0.0 to max_leverage)
        """
        vrp = self.compute_vrp()
        
        if vrp is None:
            return self.base_leverage
            
        # Calculate target leverage using VRP scaling formula
        # L_t* = min(L_max, L_base * [1 + alpha * (VRP / sigma_VRP)])
        vrp_std = np.std(self._vrp_history[-100:]) if len(self._vrp_history) >= 100 else 1.0
        
        if vrp_std < 1e-9:
            vrp_std = 1.0
            
        normalized_vrp = vrp / vrp_std
        target_leverage = self.base_leverage * (1 + self.vrp_sensitivity * normalized_vrp)
        target_leverage = min(self.max_leverage, max(1.0, target_leverage))
        
        return target_leverage
    
    def compute_vrp(self) -> Optional[float]:
        """
        Compute variance risk premium.
        
        VRP_t = IV_t^2 - RV_t^2
        
        Returns:
            Variance risk premium, or None if insufficient data
        """
        iv = self._get_implied_volatility()
        rv = self._get_realized_volatility()
        
        if iv is None or rv is None:
            return None
            
        self._iv_history.append(iv)
        self._rv_history.append(rv)
        
        vrp = (iv ** 2) - (rv ** 2)
        self._vrp_history.append(vrp)
        
        return vrp
    
    def _get_implied_volatility(self) -> Optional[float]:
        """
        Get current implied volatility.
        
        In production, this reads from CBOE VIX and listed options surfaces.
        
        Returns:
            Implied volatility (annualized), or None if unavailable
        """
        # Placeholder: simulate IV based on market state
        # In production: fetch from options data feed
        
        # Simple simulation based on average volatility feature
        if hasattr(self, '_last_state') and hasattr(self._last_state, 'features'):
            features = list(self._last_state.features.values())
            if features:
                avg_vol = np.mean([f[5] for f in features])
                return avg_vol * 252 ** 0.5  # Annualize
                
        return 0.20  # Default 20% annualized IV
    
    def _get_realized_volatility(self) -> Optional[float]:
        """
        Get current realized volatility.
        
        Uses Parkinson estimator and EWMA for robustness.
        
        Returns:
            Realized volatility (annualized), or None if unavailable
        """
        # Placeholder: simulate RV
        # In production: compute from actual price history
        
        if len(self._rv_history) > 0:
            return self._rv_history[-1]
            
        return 0.15  # Default 15% annualized RV
    
    def get_leverage_multiplier(self) -> float:
        """
        Get current leverage multiplier.
        
        Returns:
            Multiplier relative to base leverage (1.0 to L_max/L_base)
        """
        vrp = self.compute_vrp()
        
        if vrp is None:
            return 1.0
            
        vrp_std = np.std(self._vrp_history[-100:]) if len(self._vrp_history) >= 100 else 1.0
        if vrp_std < 1e-9:
            vrp_std = 1.0
            
        normalized_vrp = vrp / vrp_std
        multiplier = 1 + self.vrp_sensitivity * normalized_vrp
        
        max_multiplier = self.max_leverage / self.base_leverage
        return min(max_multiplier, max(1.0, multiplier))
    
    def is_vrp_favorable(self, threshold: float = 0.0) -> bool:
        """
        Check if VRP is favorable for leverage scaling.
        
        Args:
            threshold: Minimum VRP threshold
            
        Returns:
            True if VRP > threshold (favorable for leverage)
        """
        vrp = self.compute_vrp()
        
        if vrp is None:
            return False
            
        return vrp > threshold
    
    def force_deleverage(self) -> float:
        """
        Force immediate de-leveraging to base leverage.
        
        Called during fractured regimes or circuit breaker events.
        
        Returns:
            Base leverage level
        """
        return self.base_leverage
    
    def get_vrp_percentile(self) -> float:
        """
        Get current VRP percentile in historical distribution.
        
        Returns:
            Percentile rank (0.0 to 1.0)
        """
        if len(self._vrp_history) < 20:
            return 0.5
            
        current_vrp = self._vrp_history[-1]
        percentile = np.mean([1.0 if v < current_vrp else 0.0 for v in self._vrp_history[:-1]])
        
        return float(percentile)
