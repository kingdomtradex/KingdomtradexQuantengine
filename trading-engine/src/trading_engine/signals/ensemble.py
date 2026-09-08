"""
Multi-Agent Signal Generation Ensemble.

Coordinates four specialized agents:
- Agent 1: Micro-arbitrage (cointegrated pairs)
- Agent 2: Market-making (Avellaneda-Stoikov)
- Agent 3: TCN forecasting (10-second horizon)
- Agent 4: Volatility risk-premium scaler (leverage modulation)

Uses PPO meta-learner for dynamic weight allocation.
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AgentEnsemble:
    """
    Multi-agent ensemble with PPO-based dynamic weighting.
    
    The ensemble dynamically adjusts capital allocation to each agent
    based on trailing Sharpe ratios and regime state.
    """
    
    def __init__(self, config):
        """
        Initialize the agent ensemble.
        
        Args:
            config: System configuration
        """
        self.config = config
        
        # Initialize agents
        from .agent1_micro_arb import MicroArbitrageAgent
        from .agent2_market_maker import MarketMakingAgent
        from .agent3_tcn import TCNForecasterAgent
        from .agent4_vol_scaler import VolatilityScalerAgent
        
        self.agents = {
            0: MicroArbitrageAgent(config),      # Agent 1: Micro-arb
            1: MarketMakingAgent(config),         # Agent 2: Market-making
            2: TCNForecasterAgent(config),        # Agent 3: TCN forecast
            3: VolatilityScalerAgent(config),     # Agent 4: Vol scaler
        }
        
        # Agent weights (initialized equally, adapted by PPO)
        self.weights = np.array([0.25, 0.25, 0.25, 0.25])
        
        # Trailing Sharpe ratios for each agent
        self.trailing_sharpe = {i: 0.0 for i in range(4)}
        
        # PPO meta-learner (proprietary - simplified here)
        self._ppo_trained = False
        
        logger.info("Agent ensemble initialized with 4 agents")
    
    def generate_signals(
        self, 
        market_data: Dict[str, Any], 
        features: Dict[str, Any],
        regime_state: int
    ) -> Dict[str, Any]:
        """
        Generate composite signals from all agents.
        
        Args:
            market_data: Current market data
            features: Computed features per symbol
            regime_state: Current HMM regime state
            
        Returns:
            Dictionary containing:
            - target_positions: Target position per symbol
            - agent_weights: Current agent weights
            - leverage_multiplier: Leverage scaling factor from Agent 4
        """
        # Collect signals from each agent
        agent_signals = {}
        for agent_id, agent in self.agents.items():
            signal = agent.generate_signal(market_data, features, regime_state)
            agent_signals[agent_id] = signal
            
            # Update trailing Sharpe (simplified)
            self._update_trailing_sharpe(agent_id, signal)
        
        # Update weights via PPO meta-learner
        self._update_weights(regime_state)
        
        # Get leverage multiplier from Agent 4
        leverage_mult = agent_signals[3].get('leverage_multiplier', 1.0)
        
        # Combine signals using weights
        combined = self._combine_signals(agent_signals, leverage_mult)
        
        return {
            'target_positions': combined['positions'],
            'agent_weights': dict(enumerate(self.weights.tolist())),
            'leverage_multiplier': leverage_mult,
            'regime_gate': self._get_regime_gate(regime_state),
        }
    
    def _update_trailing_sharpe(self, agent_id: int, signal: Dict) -> None:
        """Update trailing Sharpe ratio for an agent."""
        # Simplified - in production this uses rolling window of returns
        pnl = signal.get('pnl_estimate', 0.0)
        vol = signal.get('vol_estimate', 1.0) + 1e-6
        
        # EWMA update
        sharpe = pnl / vol
        alpha = 0.1
        self.trailing_sharpe[agent_id] = (
            (1 - alpha) * self.trailing_sharpe[agent_id] + alpha * sharpe
        )
    
    def _update_weights(self, regime_state: int) -> None:
        """
        Update agent weights using PPO meta-learner logic.
        
        Weights are adjusted based on:
        - Trailing Sharpe ratios
        - Regime state (some agents perform better in certain regimes)
        """
        # Simplified softmax over Sharpe ratios
        sharpes = np.array([self.trailing_sharpe[i] for i in range(4)])
        
        # Apply regime-dependent bonuses
        regime_bonus = self._get_regime_bonus(regime_state)
        adjusted_sharpes = sharpes + regime_bonus
        
        # Softmax to get weights (simplex constraint)
        exp_sharpes = np.exp(adjusted_sharpes - np.max(adjusted_sharpes))
        self.weights = exp_sharpes / (exp_sharpes.sum() + 1e-10)
        
        # Ensure minimum weight for diversification
        self.weights = np.maximum(self.weights, 0.05)
        self.weights /= self.weights.sum()
    
    def _get_regime_bonus(self, regime_state: int) -> np.ndarray:
        """Get Sharpe bonus/penalty per agent based on regime."""
        # Bonus matrix: rows=regimes, cols=agents
        bonuses = np.array([
            [0.2, 0.1, 0.1, 0.0],   # Low-vol: favor micro-arb
            [0.0, 0.1, 0.3, -0.1],  # High-vol/trending: favor TCN
            [-0.3, -0.2, -0.1, -0.5],  # Fractured: penalize all (force de-lever)
        ])
        return bonuses[regime_state] if regime_state < len(bonuses) else np.zeros(4)
    
    def _get_regime_gate(self, regime_state: int) -> float:
        """Get regime gate multiplier (0 in fractured state)."""
        gates = [1.0, 0.5, 0.0]  # Low-vol, High-vol, Fractured
        return gates[regime_state] if regime_state < len(gates) else 0.0
    
    def _combine_signals(
        self, 
        agent_signals: Dict[int, Dict], 
        leverage_mult: float
    ) -> Dict[str, Any]:
        """Combine weighted signals into target positions."""
        all_symbols = set()
        for sig in agent_signals.values():
            all_symbols.update(sig.get('positions', {}).keys())
        
        combined_positions = {}
        for symbol in all_symbols:
            position = 0.0
            for agent_id in range(4):
                agent_pos = agent_signals[agent_id].get('positions', {}).get(symbol, 0.0)
                combined_positions[symbol] = combined_positions.get(symbol, 0.0) + \
                                            self.weights[agent_id] * agent_pos
        
        # Apply leverage multiplier from Agent 4
        for symbol in combined_positions:
            combined_positions[symbol] *= leverage_mult
        
        return {'positions': combined_positions}
