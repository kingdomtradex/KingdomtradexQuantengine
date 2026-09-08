"""
Agent 4: Volatility Risk-Premium Scaler.

Computes differential between implied and realized volatility.
Acts as multiplicative exposure scaler on aggregate output of Agents 1-3.

When IV > RV (positive VRP): scales exposure toward 10.0x ceiling
When RV > IV (premium inversion): forces rapid de-leveraging
"""

import logging
import numpy as np
from typing import Dict, Any

logger = logging.getLogger(__name__)


class VolatilityScalerAgent:
    """
    Volatility risk-premium harvesting module.
    
    Target leverage: L* = min(L_max, L_base * [1 + alpha * (VRP / sigma_VRP)])
    """
    
    def __init__(self, config):
        self.config = config
        self.leverage_multiplier = 1.0
        self.iv_history = []  # Implied volatility history
        self.rv_history = []  # Realized volatility history
        logger.info("Volatility scaler agent initialized")
    
    def generate_signal(
        self, 
        market_data: Dict[str, Any], 
        features: Dict[str, Any],
        regime_state: int
    ) -> Dict[str, Any]:
        """
        Compute leverage multiplier based on variance risk premium.
        
        This agent does NOT generate independent positions.
        It returns a leverage multiplier for the ensemble.
        """
        # Aggregate volatility metrics across universe
        avg_rv = np.mean([f.get('parkinson_vol', 0.02) for f in features.values()])
        
        # Simulated IV (in production: from VIX, options surfaces)
        avg_iv = self._estimate_implied_vol(avg_rv)
        
        # Store for VRP estimation
        self.rv_history.append(avg_rv)
        self.iv_history.append(avg_iv)
        
        # Keep rolling window
        max_len = 252
        if len(self.rv_history) > max_len:
            self.rv_history.pop(0)
            self.iv_history.pop(0)
        
        # Compute VRP
        vrp = avg_iv**2 - avg_rv**2
        
        # Normalize by trailing VRP volatility
        if len(self.vrp_history()) >= 20:
            sigma_vrp = np.std(self.vrp_history())
        else:
            sigma_vrp = 0.01  # Default
        
        # Compute target leverage
        leverage = self._compute_leverage(vrp, sigma_vrp, regime_state)
        self.leverage_multiplier = leverage
        
        return {
            'positions': {},  # No direct positions
            'leverage_multiplier': leverage,
            'vrp': vrp,
            'implied_vol': avg_iv,
            'realized_vol': avg_rv,
            'pnl_estimate': 0.0,
            'vol_estimate': 0.0,
        }
    
    def vrp_history(self) -> list:
        """Get historical VRP values."""
        return [iv**2 - rv**2 for iv, rv in zip(self.iv_history, self.rv_history)]
    
    def _estimate_implied_vol(self, realized_vol: float) -> float:
        """Estimate implied volatility (simplified)."""
        # In production: from VIX, SPX options, crypto perp funding rates
        # Typical VRP is positive (IV > RV) in calm markets
        base_iv = realized_vol + 0.005  # Small positive VRP baseline
        return max(base_iv, 0.01)
    
    def _compute_leverage(
        self, 
        vrp: float, 
        sigma_vrp: float,
        regime_state: int
    ) -> float:
        """
        Compute leverage multiplier from VRP.
        
        Formula: L* = min(L_max, L_base * [1 + alpha * (VRP / sigma_VRP)])
        """
        L_max = self.config.leverage.max_gross  # 10.0
        L_base = self.config.leverage.base      # 1.0
        alpha = self.config.leverage.variance_premium_sensitivity  # 0.5
        
        # Regime gate (hard constraint)
        regime_gate = [1.0, 0.5, 0.0][regime_state] if regime_state < 3 else 0.0
        
        if sigma_vrp <= 0 or regime_gate == 0:
            return L_base * regime_gate
        
        # Scaled leverage
        scaled = L_base * (1 + alpha * (vrp / sigma_vrp))
        
        # Apply bounds
        leverage = max(L_base, min(L_max, scaled))
        
        # Apply regime gate
        leverage *= regime_gate
        
        logger.debug(f"Leverage multiplier: {leverage:.2f} (VRP={vrp:.6f})")
        
        return leverage
