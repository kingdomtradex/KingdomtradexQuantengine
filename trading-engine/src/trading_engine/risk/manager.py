"""
Unified Risk Management Framework.

Implements hierarchical risk constraints:
- Position-level: 0.75% risk-per-trade cap
- Portfolio-level: Fractional Kelly sizing
- System-level: -2.5% daily drawdown circuit breaker
- Leverage: Dynamic scaling up to 10.0x ceiling
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Centralized risk management with hard circuit breakers.
    
    Attributes:
        config: System configuration
        observation_mode: True if system is in observation-only state
        gross_exposure: Current gross notional exposure
        net_exposure: Current net notional exposure
    """
    
    def __init__(self, config):
        self.config = config
        self.observation_mode = False
        self.gross_exposure = 0.0
        self.net_exposure = 0.0
        self.current_leverage = 1.0
        self._daily_pnl = 0.0
        
        logger.info("Risk manager initialized")
        logger.info(f"Daily drawdown limit: {config.risk.daily_drawdown_limit:.2%}")
        logger.info(f"Max leverage: {config.leverage.max_gross}x")
    
    def check_circuit_breaker(self, daily_pnl: float) -> bool:
        """
        Check if daily drawdown has triggered circuit breaker.
        
        Args:
            daily_pnl: Current daily P&L
            
        Returns:
            True if circuit breaker should trigger
        """
        self._daily_pnl = daily_pnl
        threshold = self.config.risk.daily_drawdown_limit
        
        if daily_pnl <= threshold:
            logger.critical(
                f"CIRCUIT BREAKER TRIGGERED: Daily PnL {daily_pnl:.4f} "
                f"< threshold {threshold:.4f}"
            )
            return True
        return False
    
    def get_position_size(
        self, 
        signal_strength: float, 
        volatility: float,
        capital: float
    ) -> float:
        """
        Compute position size using fractional Kelly criterion.
        
        Formula: f_deployed = λ * (μ / σ²) subject to 0.75% risk cap
        
        Args:
            signal_strength: Expected excess return (μ)
            volatility: Return variance (σ²)
            capital: Available capital
            
        Returns:
            Position size in dollar terms
        """
        if volatility <= 0:
            return 0.0
        
        # Full Kelly fraction
        kelly_fraction = signal_strength / (volatility ** 2)
        
        # Apply fractional multiplier (λ = 0.40)
        lambda_mult = self.config.risk.kelly_multiplier
        adjusted_fraction = lambda_mult * kelly_fraction
        
        # Apply risk-per-trade cap (0.75%)
        max_fraction = self.config.risk.risk_per_trade
        adjusted_fraction = max(-max_fraction, min(adjusted_fraction, max_fraction))
        
        # Convert to dollar position
        position_size = adjusted_fraction * capital
        
        return position_size
    
    def compute_dynamic_leverage(
        self, 
        vrp: float, 
        regime_gate: float
    ) -> float:
        """
        Compute target leverage based on VRP and regime.
        
        Args:
            vrp: Variance risk premium
            regime_gate: Regime gate multiplier (0-1)
            
        Returns:
            Target leverage multiplier
        """
        L_max = self.config.leverage.max_gross
        L_base = self.config.leverage.base
        alpha = self.config.leverage.variance_premium_sensitivity
        
        if regime_gate == 0:
            return L_base * regime_gate
        
        # Scaled leverage from VRP
        sigma_vrp = 0.01  # Normalization factor
        scaled = L_base * (1 + alpha * (vrp / sigma_vrp))
        
        # Bound and apply regime gate
        leverage = max(L_base, min(L_max, scaled))
        leverage *= regime_gate
        
        self.current_leverage = leverage
        return leverage
    
    def force_deleveraging(self) -> None:
        """Force immediate de-leveraging (called in fractured regime)."""
        logger.warning("Forcing immediate de-leveraging")
        self.current_leverage = 0.0
    
    def set_observation_mode(self, enabled: bool) -> None:
        """Set observation-only mode (no trading)."""
        self.observation_mode = enabled
        status = "ENABLED" if enabled else "DISABLED"
        logger.info(f"Observation mode {status}")
    
    def is_observation_mode(self) -> bool:
        """Check if system is in observation-only mode."""
        return self.observation_mode
    
    def get_gross_exposure(self) -> float:
        """Get current gross exposure."""
        return self.gross_exposure
    
    def get_net_exposure(self) -> float:
        """Get current net exposure."""
        return self.net_exposure
    
    def get_current_leverage(self) -> float:
        """Get current leverage multiplier."""
        return self.current_leverage
    
    def update_exposures(
        self, 
        positions: Dict[str, float],
        prices: Dict[str, float]
    ) -> None:
        """Update exposure metrics from positions."""
        gross = sum(abs(pos * prices.get(sym, 0)) for sym, pos in positions.items())
        net = sum(pos * prices.get(sym, 0) for sym, pos in positions.items())
        
        self.gross_exposure = gross
        self.net_exposure = net
    
    def check_margin_threshold(self, collateral: float, required: float) -> bool:
        """
        Check if margin utilization exceeds pre-emptive de-leveraging threshold.
        
        Args:
            collateral: Available collateral
            required: Required margin
            
        Returns:
            True if de-leveraging should be triggered
        """
        if collateral <= 0:
            return True
        
        utilization = required / collateral
        threshold = self.config.risk.pre_emptive_deleveraging_threshold
        
        if utilization >= threshold:
            logger.warning(
                f"Margin utilization {utilization:.1%} >= threshold {threshold:.1%}"
            )
            return True
        return False
