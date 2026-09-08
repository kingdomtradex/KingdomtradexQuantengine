"""
Four-agent signal ensemble with PPO meta-learner.

Agents:
1. MicroArbitrageAgent - Exploits basis discrepancies between cointegrated pairs
2. MarketMakingAgent - Avellaneda-Stoikov framework with dynamic quote skewing
3. TCNForecaster - Temporal Convolutional Network for price prediction (weights proprietary)
4. VolatilityRiskScaler - VRP-based exposure multiplier

The PPO meta-learner dynamically adjusts capital allocation across agents
based on trailing Sharpe ratios and regime state.
"""

from typing import Dict, Any, Optional
import numpy as np

from ..config import Config
from .agent1_micro_arb import MicroArbitrageAgent
from .agent2_market_maker import MarketMakingAgent
from .agent3_tcn import TCNForecaster
from .agent4_vol_scaler import VolatilityRiskScaler


class SignalEnsemble:
    """
    Multi-agent signal generation ensemble.
    
    Combines signals from four specialized agents with dynamic
    weighting via PPO meta-learner.
    """
    
    def __init__(self, config: Config):
        """
        Initialize signal ensemble.
        
        Args:
            config: Configuration object
        """
        self.config = config
        
        # Initialize agents
        self.agent1 = MicroArbitrageAgent(config)
        self.agent2 = MarketMakingAgent(config)
        self.agent3 = TCNForecaster(config)
        self.agent4 = VolatilityRiskScaler(config)
        
        # Agent references for iteration
        self.agents = [self.agent1, self.agent2, self.agent3, self.agent4]
        
        # PPO meta-learner weights (initialized equally)
        self.agent_weights = np.ones(4) / 4
        
        # Tracking for meta-learner
        self.agent_sharpe_history: list = []
        self._trading_window = 200  # Trades for Sharpe calculation
        
    def generate(
        self,
        state: Any
    ) -> Dict[str, np.ndarray]:
        """
        Generate signals from all agents.
        
        Args:
            state: Current market state
            
        Returns:
            Dictionary mapping instrument IDs to signal vectors [agent1, agent2, agent3, agent4]
        """
        # Get regime exposure cap
        exposure_cap = self.regime_classifier.get_exposure_cap(state.regime_state)
        
        # Collect signals from each agent
        signals = {}
        instruments = list(state.order_books.keys())
        
        for inst_id in instruments:
            agent_signals = np.zeros(4)
            
            # Agent 1: Micro-arbitrage
            agent_signals[0] = self.agent1.generate_signal(inst_id, state)
            
            # Agent 2: Market-making
            agent_signals[1] = self.agent2.generate_signal(inst_id, state)
            
            # Agent 3: TCN forecast
            agent_signals[2] = self.agent3.generate_signal(inst_id, state)
            
            # Agent 4: VRP scaler (multiplicative, not additive)
            agent_signals[3] = self.agent4.generate_signal(inst_id, state)
            
            # Apply regime cap
            if state.regime_state == 2:  # Fractured
                agent_signals *= exposure_cap
                
            signals[inst_id] = agent_signals
        
        # Update meta-learner weights periodically
        self._update_meta_weights()
        
        return signals
    
    def _update_meta_weights(self) -> None:
        """Update PPO meta-learner weights based on trailing performance."""
        if len(self.agent_sharpe_history) < self._trading_window:
            return
            
        # Calculate trailing Sharpe ratios for each agent
        sharpe_ratios = np.zeros(4)
        for i in range(4):
            returns = [s[i] for s in self.agent_sharpe_history[-self._trading_window:]]
            if np.std(returns) > 0:
                sharpe_ratios[i] = np.mean(returns) / np.std(returns)
            else:
                sharpe_ratios[i] = 0.0
        
        # Softmax to get weights (simple approximation of PPO)
        exp_sharpe = np.exp(sharpe_ratios - np.max(sharpe_ratios))
        self.agent_weights = exp_sharpe / np.sum(exp_sharpe)
        
    def update_agent_performance(self, realized_returns: np.ndarray) -> None:
        """
        Update agent performance tracking.
        
        Args:
            realized_returns: Array of realized returns per agent
        """
        self.agent_sharpe_history.append(realized_returns)
        if len(self.agent_sharpe_history) > self._trading_window:
            self.agent_sharpe_history.pop(0)
    
    @property
    def regime_classifier(self):
        """Access regime classifier from parent engine."""
        # This is set by the TradingEngine during initialization
        if not hasattr(self, '_regime_classifier'):
            from ..features.regime import RegimeClassifier
            self._regime_classifier = RegimeClassifier(self.config)
        return self._regime_classifier
