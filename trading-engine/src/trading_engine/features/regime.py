"""
Regime Classification using Hidden Markov Models.

Implements a 3-state HMM for market regime detection:
- State 0: Low-Volatility/High-Liquidity
- State 1: High-Volatility/Trending  
- State 2: Fractured/Illiquid (hard gate for risk layer)

The HMM is re-estimated daily. Posterior state probability acts as a
hard gate for the risk layer.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple
from enum import IntEnum

logger = logging.getLogger(__name__)


class HMMState(IntEnum):
    """Market regime states."""
    LOW_VOL_HIGH_LIQ = 0      # Benign - full leverage allowed
    HIGH_VOL_TRENDING = 1     # Caution - reduced leverage
    FRACTURED_ILLIQUID = 2    # Danger - force de-leveraging


class RegimeClassifier:
    """
    Hidden Markov Model-based regime classifier.
    
    Attributes:
        n_states: Number of latent states (default: 3)
        current_state: Current inferred regime state
        state_probabilities: Posterior probabilities for each state
    """
    
    def __init__(self, config):
        """
        Initialize regime classifier.
        
        Args:
            config: System configuration containing HMM parameters
        """
        self.config = config
        self.n_states = config.regime.hmm_states
        self.current_state: int = HMMState.LOW_VOL_HIGH_LIQ
        self.state_probabilities: np.ndarray = np.array([1.0, 0.0, 0.0])
        
        # HMM parameters (proprietary - loaded from secure storage in production)
        # These are placeholder values demonstrating the architecture
        self._transition_matrix: Optional[np.ndarray] = None
        self._emission_means: Optional[np.ndarray] = None
        self._emission_vars: Optional[np.ndarray] = None
        
        # Feature history for inference
        self._feature_history: list = []
        self._max_history = 252  # One trading year
        
        logger.info(f"Regime classifier initialized with {self.n_states} states")
    
    def classify(self, features: Dict[str, Any]) -> int:
        """
        Classify current market regime from features.
        
        Args:
            features: Dictionary of computed features per symbol
            
        Returns:
            Current regime state (0, 1, or 2)
        """
        # Aggregate features across universe
        aggregated = self._aggregate_features(features)
        
        # Store for online estimation
        self._feature_history.append(aggregated)
        if len(self._feature_history) > self._max_history:
            self._feature_history.pop(0)
        
        # Perform HMM inference
        if len(self._feature_history) >= 20:  # Minimum history for inference
            self.state_probabilities = self._infer_state(aggregated)
            self.current_state = int(np.argmax(self.state_probabilities))
            
            # Log regime changes
            state_name = HMMState(self.current_state).name
            prob = self.state_probabilities[self.current_state]
            logger.debug(f"Regime: {state_name} (p={prob:.3f})")
        
        return self.current_state
    
    def _aggregate_features(self, features: Dict[str, Any]) -> np.ndarray:
        """
        Aggregate per-symbol features into regime indicators.
        
        Computes universe-wide statistics:
        - Average Parkinson volatility
        - Average OFI
        - Cross-sectional volatility dispersion
        - Correlation breakdown indicator
        
        Args:
            features: Per-symbol feature dictionary
            
        Returns:
            Aggregated feature vector for HMM observation
        """
        if not features:
            return np.zeros(4)
        
        parkinson_vols = [f['parkinson_vol'] for f in features.values()]
        ofis = [f['ofi'] for f in features.values()]
        quote_slopes = [f['quote_slope'] for f in features.values()]
        spread_persistences = [f['spread_persistence'] for f in features.values()]
        
        # Mean volatility
        avg_vol = np.mean(parkinson_vols) if parkinson_vols else 0.0
        
        # Volatility dispersion (cross-sectional)
        vol_dispersion = np.std(parkinson_vols) if len(parkinson_vols) > 1 else 0.0
        
        # Net order flow imbalance
        net_ofi = np.mean(ofis) if ofis else 0.0
        
        # Liquidity stress (low spread persistence = fragmentation)
        liquidity_stress = 1.0 - np.mean(spread_persistences) if spread_persistences else 0.0
        
        return np.array([avg_vol, vol_dispersion, net_ofi, liquidity_stress])
    
    def _infer_state(self, observation: np.ndarray) -> np.ndarray:
        """
        Infer posterior state probabilities given observation.
        
        Uses forward algorithm for HMM filtering.
        
        Args:
            observation: Current aggregated feature vector
            
        Returns:
            Posterior probabilities over states
        """
        # Initialize HMM parameters if not loaded
        if self._transition_matrix is None:
            self._initialize_hmm_parameters()
        
        # Simplified forward step (production uses full forward-backward)
        # alpha_t = alpha_{t-1} @ A * P(observation | state)
        
        n_obs = len(observation)
        
        # Compute emission probabilities (Gaussian)
        emissions = np.zeros(self.n_states)
        for s in range(self.n_states):
            mean = self._emission_means[s, :n_obs]
            var = self._emission_vars[s, :n_obs] + 1e-6
            log_prob = -0.5 * np.sum((observation - mean)**2 / var) - 0.5 * np.sum(np.log(var))
            emissions[s] = np.exp(log_prob)
        
        # Bayesian update with transition prior
        prior = self.state_probabilities @ self._transition_matrix
        posterior = prior * emissions
        posterior /= posterior.sum() + 1e-10
        
        return posterior
    
    def _initialize_hmm_parameters(self) -> None:
        """
        Initialize HMM parameters.
        
        In production, these are estimated from historical data
        and loaded from secure storage. Parameters are re-estimated daily.
        """
        # Placeholder transition matrix (diagonal-dominant for persistence)
        # Rows sum to 1
        self._transition_matrix = np.array([
            [0.95, 0.04, 0.01],  # Low-vol tends to persist
            [0.10, 0.80, 0.10],  # High-vol has moderate persistence
            [0.05, 0.15, 0.80],  # Fractured state somewhat persistent
        ])
        
        # Emission means per state (vol, vol_dispersion, ofi, liquidity_stress)
        self._emission_means = np.array([
            [0.01, 0.005, 0.0, 0.1],   # State 0: Low vol, low stress
            [0.03, 0.015, 0.5, 0.3],   # State 1: Higher vol, trending
            [0.08, 0.04, 2.0, 0.7],    # State 2: High vol, fragmented
        ])
        
        # Emission variances
        self._emission_vars = np.array([
            [0.005**2, 0.003**2, 0.5**2, 0.1**2],
            [0.01**2, 0.008**2, 1.0**2, 0.2**2],
            [0.02**2, 0.015**2, 2.0**2, 0.3**2],
        ])
        
        logger.debug("HMM parameters initialized")
    
    def reestimate_daily(self, returns_history: np.ndarray) -> None:
        """
        Re-estimate HMM parameters using daily returns.
        
        Called once per day at market close.
        
        Args:
            returns_history: T x N array of returns (T days, N instruments)
        """
        logger.info("Re-estimating HMM parameters...")
        
        # In production, this runs Baum-Welch algorithm
        # For now, we use simplified method-of-moments estimation
        
        # Compute realized volatility regimes
        daily_vol = np.std(returns_history, axis=1)
        
        # Update emission means based on observed volatility quantiles
        q33 = np.percentile(daily_vol, 33)
        q66 = np.percentile(daily_vol, 66)
        
        self._emission_means[0, 0] = daily_vol[daily_vol <= q33].mean()
        self._emission_means[1, 0] = daily_vol[(daily_vol > q33) & (daily_vol <= q66)].mean()
        self._emission_means[2, 0] = daily_vol[daily_vol > q66].mean()
        
        logger.info("HMM parameter re-estimation complete")
    
    def get_regime_gate_multiplier(self) -> float:
        """
        Get leverage gate multiplier based on current regime.
        
        Returns:
            Multiplier (0.0 to 1.0) applied to maximum leverage
        """
        # Hard gating based on regime state
        multipliers = {
            HMMState.LOW_VOL_HIGH_LIQ: 1.0,      # Full leverage allowed
            HMMState.HIGH_VOL_TRENDING: 0.5,     # Half leverage
            HMMState.FRACTURED_ILLIQUID: 0.0,    # Force flat
        }
        return multipliers.get(HMMState(self.current_state), 0.0)
