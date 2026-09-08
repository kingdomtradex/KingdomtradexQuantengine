"""
Portfolio Construction with Risk Constraints.

Consolidates signals into unified portfolio with:
- USD-equivalent delta/gamma/vega sensitivities
- Fractional Kelly position sizing
- Dynamic leverage scaling
- Cross-asset beta hedging
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PortfolioConstructor:
    """
    Portfolio construction layer with integrated risk constraints.
    
    Enforces systematic beta hedging to isolate alpha from market exposure.
    """
    
    def __init__(self, config, risk_manager):
        """
        Initialize portfolio constructor.
        
        Args:
            config: System configuration
            risk_manager: RiskManager instance for constraints
        """
        self.config = config
        self.risk_manager = risk_manager
        self.target_beta = 0.0
        self.max_beta = 0.05
        
        logger.info("Portfolio constructor initialized")
    
    def construct(
        self, 
        signals: Dict[str, Any],
        regime_state: int,
        daily_pnl: float
    ) -> Dict[str, float]:
        """
        Construct target portfolio from signals.
        
        Args:
            signals: Signal dictionary from ensemble
            regime_state: Current HMM regime state
            daily_pnl: Current daily P&L
            
        Returns:
            Dictionary of target positions per symbol
        """
        # Check circuit breaker first
        if self.risk_manager.check_circuit_breaker(daily_pnl):
            logger.critical("Circuit breaker triggered - returning flat portfolio")
            return {}
        
        # Get raw target positions
        target_positions = signals.get('target_positions', {})
        
        # Apply regime gate
        regime_gate = signals.get('regime_gate', 1.0)
        if regime_gate == 0:
            return {}
        
        # Apply leverage multiplier from Agent 4
        leverage_mult = signals.get('leverage_multiplier', 1.0)
        
        # Scale positions by leverage and regime
        scaled_positions = {
            sym: pos * leverage_mult * regime_gate
            for sym, pos in target_positions.items()
        }
        
        # Apply Kelly-based position sizing
        sized_positions = self._apply_kelly_sizing(scaled_positions)
        
        # Beta hedge if needed
        hedged_positions = self._apply_beta_hedge(sized_positions)
        
        return hedged_positions
    
    def _apply_kelly_sizing(self, positions: Dict[str, float]) -> Dict[str, float]:
        """Apply fractional Kelly sizing to positions."""
        sized = {}
        capital = self.config.capacity_aum / self.config.leverage.max_gross
        
        for symbol, raw_pos in positions.items():
            # Simplified signal strength and vol estimates
            signal_strength = 0.001 * raw_pos  # 10 bps expected return
            volatility = 0.02  # 2% daily vol
            
            size = self.risk_manager.get_position_size(
                signal_strength, volatility, capital
            )
            sized[symbol] = size
        
        return sized
    
    def _apply_beta_hedge(self, positions: Dict[str, float]) -> Dict[str, float]:
        """
        Apply systematic beta hedging.
        
        If aggregate beta to composite benchmark exceeds 0.05,
        initiate hedges using inverse-correlation instruments.
        """
        # Simplified beta calculation
        # In production: uses Ledoit-Wolf shrunk correlation matrix
        portfolio_beta = self._estimate_portfolio_beta(positions)
        
        if abs(portfolio_beta) > self.max_beta:
            logger.info(f"Portfolio beta {portfolio_beta:.3f} exceeds threshold - hedging")
            
            # Add hedge positions (simplified)
            # In production: short VIX futures against long equity, etc.
            hedge_symbol = "HEDGE_INSTRUMENT"
            hedge_notional = -portfolio_beta * 10000  # Simplified
            
            positions[hedge_symbol] = hedge_notional
        
        return positions
    
    def _estimate_portfolio_beta(self, positions: Dict[str, float]) -> float:
        """Estimate portfolio beta to composite benchmark."""
        # Simplified - in production uses full covariance matrix
        # Default betas per asset class
        asset_class_betas = {
            'EQ': 1.0,      # Equities
            'ETF': 0.9,     # ETFs
            'FUT': 0.5,     # Futures
            'CRYPTO': 1.5,  # Crypto
        }
        
        total_beta = 0.0
        total_notional = 0.0
        
        for symbol, pos in positions.items():
            # Infer asset class from symbol (simplified)
            if 'BTC' in symbol or 'ETH' in symbol:
                beta = asset_class_betas['CRYPTO']
            elif 'FUT' in symbol:
                beta = asset_class_betas['FUT']
            elif 'ETF' in symbol:
                beta = asset_class_betas['ETF']
            else:
                beta = asset_class_betas['EQ']
            
            total_beta += beta * abs(pos)
            total_notional += abs(pos)
        
        if total_notional == 0:
            return 0.0
        
        return total_beta / total_notional
