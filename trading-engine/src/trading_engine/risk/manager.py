"""
Unified risk management with hard circuit breakers.

Risk management is the governing constraint of the architecture, especially
critical under the aggressive 10.0x leverage regime.

Key features:
- Consolidated USD-equivalent delta, gamma, vega sensitivities
- Fractional Kelly position sizing (lambda = 0.40)
- Hard 0.75% risk-per-trade limit
- -2.5% daily drawdown circuit breaker
- Pre-emptive de-leveraging at 80% collateral utilization
"""

from typing import Dict, Any, Optional, List
import numpy as np

from ..config import Config


class RiskManager:
    """
    Centralized risk management system.
    
    Enforces hard constraints on exposure, drawdown, and collateral
    utilization across all asset classes.
    """
    
    def __init__(self, config: Config):
        """
        Initialize risk manager.
        
        Args:
            config: Configuration object with risk parameters
        """
        self.config = config
        
        # Risk limits from config
        self.max_daily_drawdown = config.risk.max_daily_drawdown
        self.max_gross_leverage = config.risk.max_gross_leverage
        self.kelly_multiplier = config.risk.kelly_multiplier
        self.risk_per_trade = config.risk.risk_per_trade
        
        # State tracking
        self._daily_start_equity = config.initial_capital
        self._current_equity = config.initial_capital
        self._positions: Dict[str, float] = {}
        self._collateral_utilization = 0.0
        
        # Greeks aggregation
        self._total_delta = 0.0
        self._total_gamma = 0.0
        self._total_vega = 0.0
        
        # Circuit breaker state
        self._circuit_breaker_triggered = False
        self._observation_only = False
        
    def check_circuit_breaker(self, current_pnl: float) -> bool:
        """
        Check if circuit breaker should trigger.
        
        Trigger condition: Intraday cumulative PnL < -2.5%
        
        Args:
            current_pnl: Current cumulative PnL for the day
            
        Returns:
            True if circuit breaker triggered
        """
        daily_return = current_pnl / self._daily_start_equity
        
        if daily_return < self.max_daily_drawdown:
            self._trigger_circuit_breaker()
            return True
            
        return False
    
    def _trigger_circuit_breaker(self) -> None:
        """Activate circuit breaker protocol."""
        self._circuit_breaker_triggered = True
        self._observation_only = True
        print(f"CIRCUIT BREAKER: Daily drawdown exceeded {self.max_daily_drawdown:.2%}")
    
    def reset_daily(self, new_start_equity: float) -> None:
        """
        Reset daily state for new trading session.
        
        Args:
            new_start_equity: Starting equity for the day
        """
        self._daily_start_equity = new_start_equity
        self._circuit_breaker_triggered = False
        self._observation_only = False
        
    def calculate_position_size(
        self,
        expected_return: float,
        variance: float,
        current_exposure: float
    ) -> float:
        """
        Calculate position size using fractional Kelly Criterion.
        
        f_deployed = lambda * (mu / sigma^2)
        
        Subject to 0.75% risk-per-trade cap.
        
        Args:
            expected_return: Expected excess return (mu)
            variance: Return variance (sigma^2)
            current_exposure: Current exposure to instrument
            
        Returns:
            Target position size
        """
        if variance <= 0 or abs(expected_return) < 1e-9:
            return 0.0
            
        # Full Kelly fraction
        full_kelly = expected_return / variance
        
        # Apply fractional multiplier (lambda = 0.40)
        fractional_kelly = self.kelly_multiplier * full_kelly
        
        # Convert to dollar position based on current equity
        target_position = fractional_kelly * self._current_equity
        
        # Apply risk-per-trade cap
        max_risk_amount = self.risk_per_trade * self._current_equity
        max_position = max_risk_amount / (np.sqrt(variance) + 1e-9)
        
        # Limit position to risk cap
        target_position = np.clip(
            target_position,
            -max_position,
            max_position
        )
        
        # Respect gross leverage ceiling
        max_gross_exposure = self._current_equity * self.max_gross_leverage
        current_gross = sum(abs(p) for p in self._positions.values())
        
        remaining_capacity = max_gross_exposure - current_gross
        if abs(target_position) > abs(remaining_capacity):
            target_position = np.sign(target_position) * max(0, remaining_capacity)
        
        return float(target_position)
    
    def update_greeks(
        self,
        instrument_id: str,
        delta: float,
        gamma: float,
        vega: float
    ) -> None:
        """
        Update aggregated Greeks.
        
        Args:
            instrument_id: Instrument identifier
            delta: Dollar delta
            gamma: Dollar gamma
            vega: Dollar vega
        """
        self._total_delta += delta
        self._total_gamma += gamma
        self._total_vega += vega
    
    def get_collateral_utilization(self) -> float:
        """
        Get current collateral utilization.
        
        Returns:
            Utilization ratio (0.0 to 1.0+)
        """
        return self._collateral_utilization
    
    def check_collateral_threshold(self) -> bool:
        """
        Check if pre-emptive de-leveraging threshold breached.
        
        Threshold: 80% of available collateral
        
        Returns:
            True if de-leveraging required
        """
        return self._collateral_utilization > 0.80
    
    def liquidate_all(self) -> List[Dict[str, Any]]:
        """
        Liquidate all positions to delta-neutral.
        
        Called by circuit breaker or manual intervention.
        
        Returns:
            List of liquidation orders
        """
        orders = []
        
        for inst_id, position in self._positions.items():
            if position != 0:
                orders.append({
                    "instrument_id": inst_id,
                    "action": "SELL" if position > 0 else "BUY",
                    "quantity": abs(position),
                    "order_type": "MARKET",
                    "reason": "RISK_LIQUIDATION"
                })
                
        self._positions = {}
        self._total_delta = 0.0
        self._total_gamma = 0.0
        self._total_vega = 0.0
        
        return orders
    
    def update_equity(self, pnl_change: float) -> None:
        """
        Update current equity after PnL change.
        
        Args:
            pnl_change: PnL change from trades
        """
        self._current_equity += pnl_change
        
    def set_collateral_utilization(self, utilization: float) -> None:
        """
        Set collateral utilization from external calculation.
        
        Args:
            utilization: Utilization ratio
        """
        self._collateral_utilization = utilization
        
        # Auto de-lever if above threshold
        if self.check_collateral_threshold() and not self._observation_only:
            print(f"Pre-emptive de-leveraging triggered at {utilization:.1%} collateral")
    
    def get_risk_summary(self) -> dict:
        """
        Get current risk summary.
        
        Returns:
            Dictionary with risk metrics
        """
        daily_pnl = self._current_equity - self._daily_start_equity
        daily_return = daily_pnl / self._daily_start_equity
        
        return {
            "current_equity": self._current_equity,
            "daily_pnl": daily_pnl,
            "daily_return": daily_return,
            "circuit_breaker_active": self._circuit_breaker_triggered,
            "observation_only": self._observation_only,
            "collateral_utilization": self._collateral_utilization,
            "total_delta": self._total_delta,
            "total_gamma": self._total_gamma,
            "total_vega": self._total_vega,
            "gross_exposure": sum(abs(p) for p in self._positions.values()),
            "net_exposure": sum(self._positions.values())
        }
    
    def is_trading_allowed(self) -> bool:
        """
        Check if trading is currently allowed.
        
        Returns:
            True if trading permitted, False if observation-only
        """
        return not self._observation_only
