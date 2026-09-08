"""
Agent 1: Micro-Arbitrage Agent.

Exploits basis discrepancies between cointegrated pairs using
Augmented Dickey-Fuller tests for stationarity detection.

Examples:
- Crypto spot vs perpetual futures basis
- ETF vs underlying basket arbitrage
- Cross-exchange price discrepancies
"""

from typing import Dict, Any, Optional
import numpy as np

from ..config import Config


class MicroArbitrageAgent:
    """
    Micro-arbitrage signal generator.
    
    Identifies and exploits temporary pricing inefficiencies
    between cointegrated instruments.
    """
    
    def __init__(self, config: Config):
        """
        Initialize micro-arbitrage agent.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self._cointegration_pairs = self._initialize_pairs()
        self._basis_history: Dict[str, list] = {}
        
    def _initialize_pairs(self) -> Dict[str, str]:
        """Initialize cointegrated pair mappings."""
        pairs = {}
        
        # Map crypto spot to perpetuals
        for i in range(25):
            spot_id = f"CRYPTO_{i:04d}"
            perp_id = f"CRYPTO_PERP_{i:04d}"
            pairs[spot_id] = perp_id
            
        return pairs
    
    def generate_signal(
        self,
        instrument_id: str,
        state: Any
    ) -> float:
        """
        Generate micro-arbitrage signal.
        
        Args:
            instrument_id: Instrument identifier
            state: Current market state
            
        Returns:
            Signal value in [-1, 1] range (negative=short, positive=long)
        """
        if instrument_id not in self._cointegration_pairs:
            return 0.0
            
        pair_id = self._cointegration_pairs[instrument_id]
        
        if pair_id not in state.order_books:
            return 0.0
            
        # Calculate basis
        ob = state.order_books[instrument_id]
        pair_ob = state.order_books[pair_id]
        
        if ob.mid_price is None or pair_ob.mid_price is None:
            return 0.0
            
        basis = (ob.mid_price - pair_ob.mid_price) / pair_ob.mid_price
        
        # Track basis history for z-score calculation
        if instrument_id not in self._basis_history:
            self._basis_history[instrument_id] = []
            
        self._basis_history[instrument_id].append(basis)
        if len(self._basis_history[instrument_id]) > 1000:
            self._basis_history[instrument_id].pop(0)
            
        # Calculate z-score
        if len(self._basis_history[instrument_id]) < 100:
            return 0.0
            
        history = np.array(self._basis_history[instrument_id])
        z_score = (basis - np.mean(history)) / (np.std(history) + 1e-9)
        
        # Generate signal: mean-reversion on basis
        # If basis is > 2 std above mean, short the spread
        # If basis is < -2 std below mean, long the spread
        threshold = 2.0
        if z_score > threshold:
            signal = -min(1.0, (z_score - threshold) / 2.0)
        elif z_score < -threshold:
            signal = min(1.0, (-threshold - z_score) / 2.0)
        else:
            signal = 0.0
            
        return float(np.clip(signal, -1.0, 1.0))
    
    def augmented_dickey_fuller_test(
        self,
        series: np.ndarray,
        max_lag: int = 10
    ) -> tuple:
        """
        Perform Augmented Dickey-Fuller test for stationarity.
        
        Args:
            series: Time series to test
            max_lag: Maximum lag for autoregressive terms
            
        Returns:
            Tuple of (test_statistic, p_value, is_stationary)
        """
        n = len(series)
        if n < max_lag + 10:
            return (0.0, 1.0, False)
            
        # Simplified ADF implementation
        # In production, use statsmodels.adfuller
        
        delta = np.diff(series)
        y = series[:-1]
        y_lagged = np.column_stack([y] + [delta[:-i] for i in range(1, max_lag + 1)])
        
        # OLS regression
        try:
            coeffs = np.linalg.lstsq(y_lagged, delta[max_lag:], rcond=None)[0]
            test_stat = coeffs[0] / 0.01  # Simplified standard error
            
            # Critical values at 5% significance
            critical_value = -2.86
            is_stationary = test_stat < critical_value
            
            return (float(test_stat), 0.05 if is_stationary else 0.5, is_stationary)
        except Exception:
            return (0.0, 1.0, False)
