"""
Portfolio construction with systematic beta hedging.

Constructs optimal portfolio from agent signals while enforcing:
- Unit-of-Risk normalization across asset classes
- Fractional Kelly position sizing
- Gross leverage ceiling (dynamic, VRP-gated)
- Systematic beta hedging to isolate alpha from market exposure
"""

from typing import Dict, Any, Optional, List, Tuple
import numpy as np

from ..config import Config


class PortfolioConstructor:
    """
    Portfolio construction engine.
    
    Combines signals from the four-agent ensemble into a unified portfolio
    with risk constraints and beta hedging.
    """
    
    def __init__(self, config: Config):
        """
        Initialize portfolio constructor.
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Correlation matrix for cross-asset risk management
        self._correlation_matrix: Optional[np.ndarray] = None
        self._instrument_ids: List[str] = []
        
        # Beta hedging parameters
        self.max_portfolio_beta = 0.05  # Maximum net beta to benchmark
        
    def construct(
        self,
        signals: Dict[str, np.ndarray],
        state: Any,
        current_positions: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Construct target portfolio from signals.
        
        Args:
            signals: Agent signals per instrument [4 agents]
            state: Current market state
            current_positions: Existing positions
            
        Returns:
            Dictionary mapping instrument IDs to target positions
        """
        if not signals:
            return {}
            
        # Get regime-adjusted leverage multiplier
        leverage_mult = self._get_leverage_multiplier(state)
        
        # Build target positions
        targets = {}
        instruments = list(signals.keys())
        
        for inst_id in instruments:
            agent_signals = signals[inst_id]
            
            # Weighted combination of agent signals
            # In production, uses PPO meta-learner weights
            combined_signal = np.mean(agent_signals[:3])  # Agents 1-3
            vrp_multiplier = agent_signals[3] if len(agent_signals) > 3 else 1.0
            
            # Apply VRP scaling
            scaled_signal = combined_signal * vrp_multiplier
            
            # Apply regime cap
            if state.regime_state == 2:  # Fractured
                scaled_signal *= 0.2
                
            # Calculate target position
            if abs(scaled_signal) > 0.01:
                position = self._calculate_target_position(
                    instrument_id=inst_id,
                    signal=scaled_signal,
                    state=state,
                    leverage_mult=leverage_mult
                )
                targets[inst_id] = position
            else:
                targets[inst_id] = 0.0
                
        # Apply beta hedging
        targets = self._apply_beta_hedging(targets, state)
        
        # Enforce gross leverage limit
        targets = self._enforce_leverage_limit(targets, state.current_pnl)
        
        return targets
    
    def _get_leverage_multiplier(self, state: Any) -> float:
        """Get leverage multiplier based on VRP and regime."""
        # Base multiplier from VRP
        base_mult = 1.0 + state.variance_risk_premium * 5.0
        
        # Regime adjustment
        if state.regime_state == 0:  # Low-Vol
            regime_cap = 1.0
        elif state.regime_state == 1:  # High-Vol
            regime_cap = 0.5
        else:  # Fractured
            regime_cap = 0.2
            
        return min(base_mult, regime_cap * self.config.leverage.max_leverage)
    
    def _calculate_target_position(
        self,
        instrument_id: str,
        signal: float,
        state: Any,
        leverage_mult: float
    ) -> float:
        """
        Calculate target position for single instrument.
        
        Uses Unit-of-Risk normalization for cross-asset comparability.
        """
        if instrument_id not in state.features:
            return 0.0
            
        features = state.features[instrument_id]
        volatility = features[5]  # Volatility estimate
        
        if volatility <= 0:
            return 0.0
            
        # Unit-of-Risk: notional per 1 std dev
        unit_risk_notional = self.config.initial_capital * 0.01 / volatility
        
        # Scale by signal strength and leverage
        target = unit_risk_notional * signal * leverage_mult
        
        # Apply risk-per-trade cap
        max_position = self.config.risk.risk_per_trade * self.config.initial_capital / volatility
        target = np.clip(target, -max_position, max_position)
        
        return float(target)
    
    def _apply_beta_hedging(
        self,
        targets: Dict[str, float],
        state: Any
    ) -> Dict[str, float]:
        """
        Apply systematic beta hedging.
        
        If portfolio beta exceeds threshold, initiate hedges using
        inverse-correlation instruments (e.g., short VIX futures).
        """
        if not targets:
            return targets
            
        # Estimate portfolio beta (simplified)
        portfolio_beta = self._estimate_portfolio_beta(targets, state)
        
        if abs(portfolio_beta) > self.max_portfolio_beta:
            # Need to hedge
            hedge_direction = -np.sign(portfolio_beta)
            
            # Find hedging instrument (simplified: use first crypto as proxy)
            hedge_inst = None
            for inst_id in targets.keys():
                if "CRYPTO" in inst_id or "FUTURE" in inst_id:
                    hedge_inst = inst_id
                    break
                    
            if hedge_inst:
                # Add hedge position proportional to beta excess
                hedge_size = abs(portfolio_beta) * sum(abs(p) for p in targets.values()) * 0.1
                targets[hedge_inst] = targets.get(hedge_inst, 0.0) + hedge_direction * hedge_size
                
        return targets
    
    def _estimate_portfolio_beta(
        self,
        targets: Dict[str, float],
        state: Any
    ) -> float:
        """
        Estimate portfolio beta to composite benchmark.
        
        Simplified implementation using correlation proxy.
        """
        if not targets or self._correlation_matrix is None:
            return 0.0
            
        # Simplified: average correlation as beta proxy
        total_exposure = sum(abs(p) for p in targets.values())
        if total_exposure == 0:
            return 0.0
            
        # Assume average beta of 0.8 for equities, 0.3 for crypto
        beta = 0.0
        for inst_id, pos in targets.items():
            if "EQUITY" in inst_id:
                beta += 0.8 * abs(pos)
            elif "CRYPTO" in inst_id:
                beta += 0.3 * abs(pos)
            else:
                beta += 0.5 * abs(pos)
                
        return beta / total_exposure
    
    def _enforce_leverage_limit(
        self,
        targets: Dict[str, float],
        current_pnl: float
    ) -> Dict[str, float]:
        """
        Enforce gross leverage ceiling.
        
        Scales down all positions proportionally if gross exposure
        exceeds maximum allowed leverage.
        """
        gross_exposure = sum(abs(p) for p in targets.values())
        max_gross = self.config.initial_capital * self.config.leverage.max_leverage
        
        if gross_exposure > max_gross:
            scale_factor = max_gross / gross_exposure
            targets = {k: v * scale_factor for k, v in targets.items()}
            
        return targets
    
    def update_correlation_matrix(
        self,
        returns_data: np.ndarray,
        instrument_ids: List[str]
    ) -> None:
        """
        Update Ledoit-Wolf shrunk correlation matrix.
        
        Args:
            returns_data: Matrix of returns [time, instruments]
            instrument_ids: Instrument identifiers
        """
        if returns_data.shape[0] < 10:
            return
            
        # Compute sample covariance
        sample_cov = np.cov(returns_data.T)
        
        # Ledoit-Wolf shrinkage (simplified)
        n = returns_data.shape[1]
        target = np.eye(n) * np.mean(np.diag(sample_cov))
        
        # Shrinkage intensity
        shrinkage = 0.2  # Simplified; actual calculation more complex
        
        shrunk_cov = shrinkage * target + (1 - shrinkage) * sample_cov
        
        # Convert to correlation
        std_devs = np.sqrt(np.diag(shrunk_cov))
        self._correlation_matrix = shrunk_cov / np.outer(std_devs, std_devs)
        self._instrument_ids = instrument_ids
