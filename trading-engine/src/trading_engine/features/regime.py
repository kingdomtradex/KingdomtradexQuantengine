"""
Regime classification using Hidden Markov Models.

Implements a 3-state HMM for market regime detection:
- State 0: Low-Volatility / High-Liquidity
- State 1: High-Volatility / Trending
- State 2: Fractured / Illiquid

The posterior state probability acts as a hard gate for risk limits.
In State 2 (Fractured), the system automatically de-levers and disables
passive market-making to avoid toxic order flow.

Note: Exact HMM parameters are proprietary and loaded from secure storage
in production. This implementation uses simplified initialization.
"""

from typing import Dict, Any, Tuple
import numpy as np

from ..config import Config


class RegimeClassifier:
    """
    Hidden Markov Model regime classifier.
    
    Classifies market state into one of three regimes based on
    microstructure and macro features.
    """
    
    def __init__(self, config: Config):
        """
        Initialize regime classifier.
        
        Args:
            config: Configuration object with HMM parameters
        """
        self.config = config
        self.n_states = config.hmm.n_states
        
        # State names for reference
        self.state_names = {
            0: "Low-Volatility/High-Liquidity",
            1: "High-Volatility/Trending",
            2: "Fractured/Illiquid"
        }
        
        # Initialize HMM parameters (simplified for open-source)
        # In production, these are loaded from secure parameter storage
        self._initialize_parameters()
        
        # State history for smoothing
        self._state_history: list = []
        self._observation_history: list = []
        
    def _initialize_parameters(self) -> None:
        """Initialize HMM parameters."""
        # Transition matrix (probability of moving from state i to j)
        # Diagonal dominance reflects regime persistence
        self.transition_matrix = np.array([
            [0.85, 0.10, 0.05],  # From Low-Vol
            [0.15, 0.70, 0.15],  # From High-Vol
            [0.10, 0.20, 0.70]   # From Fractured
        ])
        
        # Initial state distribution
        self.initial_distribution = np.array([0.6, 0.3, 0.1])
        
        # Emission parameters (Gaussian means and variances for each state)
        # Features: [volatility, spread, correlation, volume_imbalance]
        self.emission_means = np.array([
            [0.1, 0.001, 0.3, 0.0],   # Low-Vol: low vol, tight spreads
            [0.4, 0.003, 0.5, 0.2],   # High-Vol: elevated vol, trending
            [0.8, 0.010, 0.9, 0.5]    # Fractured: high vol, wide spreads
        ])
        
        self.emission_vars = np.array([
            [0.02, 0.0001, 0.1, 0.1],
            [0.05, 0.0005, 0.15, 0.2],
            [0.10, 0.0010, 0.2, 0.3]
        ])
        
    def classify(
        self,
        features: Dict[str, np.ndarray]
    ) -> Tuple[int, np.ndarray]:
        """
        Classify current market regime.
        
        Args:
            features: Dictionary mapping instrument IDs to feature vectors
            
        Returns:
            Tuple of (most_likely_state, state_probabilities)
        """
        # Aggregate features across universe
        aggregated = self._aggregate_features(features)
        
        # Compute emission probabilities
        emission_probs = self._compute_emission_probabilities(aggregated)
        
        # Apply forward algorithm step
        state_probs = self._forward_step(emission_probs)
        
        # Get most likely state
        most_likely_state = int(np.argmax(state_probs))
        
        # Update history
        self._state_history.append(most_likely_state)
        self._observation_history.append(aggregated)
        
        return most_likely_state, state_probs
    
    def _aggregate_features(
        self,
        features: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """
        Aggregate features across instrument universe.
        
        Args:
            features: Per-instrument feature vectors
            
        Returns:
            Aggregated feature vector [volatility, spread, correlation, volume_imbalance]
        """
        if not features:
            return np.zeros(4)
            
        feature_array = np.array(list(features.values()))
        
        # Mean volatility (feature 5)
        avg_vol = np.mean(feature_array[:, 5])
        
        # Mean relative spread (feature 2 inverted)
        avg_spread = np.mean(1.0 - feature_array[:, 2])
        
        # Correlation proxy (variance of OFI across instruments)
        correlation = np.var(feature_array[:, 0])
        
        # Volume imbalance
        volume_imbalance = np.mean(
            np.abs(feature_array[:, 3] - feature_array[:, 4]) / 
            (feature_array[:, 3] + feature_array[:, 4] + 1e-9)
        )
        
        return np.array([avg_vol, avg_spread, correlation, volume_imbalance])
    
    def _compute_emission_probabilities(
        self,
        observation: np.ndarray
    ) -> np.ndarray:
        """
        Compute emission probabilities for observation.
        
        Args:
            observation: Feature vector
            
        Returns:
            Probability of observation under each state
        """
        probs = np.zeros(self.n_states)
        
        for state in range(self.n_states):
            mean = self.emission_means[state]
            var = self.emission_vars[state]
            
            # Gaussian emission probability
            diff = observation - mean
            log_prob = -0.5 * np.sum((diff ** 2) / (var + 1e-9))
            log_prob -= 0.5 * np.sum(np.log(var + 1e-9))
            
            probs[state] = np.exp(log_prob)
        
        # Normalize
        prob_sum = np.sum(probs)
        if prob_sum > 0:
            probs /= prob_sum
            
        return probs
    
    def _forward_step(
        self,
        emission_probs: np.ndarray
    ) -> np.ndarray:
        """
        Perform one step of the forward algorithm.
        
        Args:
            emission_probs: Emission probabilities for current observation
            
        Returns:
            Updated state probabilities
        """
        if not self._state_history:
            # First observation: use initial distribution
            probs = self.initial_distribution * emission_probs
        else:
            # Use previous state probabilities
            prev_probs = self._get_previous_state_probs()
            probs = prev_probs @ self.transition_matrix * emission_probs
        
        # Normalize
        prob_sum = np.sum(probs)
        if prob_sum > 0:
            probs /= prob_sum
        else:
            probs = self.initial_distribution
            
        return probs
    
    def _get_previous_state_probs(self) -> np.ndarray:
        """Get previous state probabilities from history."""
        if not self._state_history:
            return self.initial_distribution
            
        # Simple approach: use indicator of last state
        last_state = self._state_history[-1]
        probs = np.zeros(self.n_states)
        probs[last_state] = 1.0
        return probs
    
    def get_exposure_cap(self, state: int) -> float:
        """
        Get exposure cap for given regime state.
        
        Args:
            state: Regime state index
            
        Returns:
            Exposure cap multiplier (0.0 to 1.0)
        """
        thresholds = self.config.hmm.regime_thresholds
        
        if state == 0:  # Low-Volatility
            return thresholds.get("low_vol_exposure_cap", 1.0)
        elif state == 1:  # High-Volatility
            return thresholds.get("high_vol_exposure_cap", 0.5)
        else:  # Fractured
            return thresholds.get("fractured_exposure_cap", 0.2)
    
    def reset(self) -> None:
        """Reset classifier state."""
        self._state_history = []
        self._observation_history = []
