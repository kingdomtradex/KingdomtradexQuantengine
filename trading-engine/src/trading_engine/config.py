"""
Configuration management for the trading engine.

Loads and validates configuration parameters from YAML files.
All risk parameters are pre-commitment locked per the technical specification.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

import yaml


@dataclass
class RiskConfig:
    """Risk management configuration parameters."""
    max_daily_drawdown: float = -0.025  # Circuit breaker trigger
    max_gross_leverage: float = 10.0    # Ceiling for dynamic leverage
    kelly_multiplier: float = 0.40      # Fractional Kelly lambda
    risk_per_trade: float = 0.0075      # 0.75% hard limit


@dataclass
class LeverageConfig:
    """Dynamic leverage scaling parameters."""
    base_leverage: float = 1.0
    vrp_sensitivity: float = 0.5
    max_leverage: float = 10.0


@dataclass
class HMMConfig:
    """Hidden Markov Model regime classifier parameters."""
    n_states: int = 3
    regime_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "fractured_exposure_cap": 0.2,
        "high_vol_exposure_cap": 0.5,
        "low_vol_exposure_cap": 1.0
    })


@dataclass
class ExecutionConfig:
    """Smart order routing and execution parameters."""
    twap_slices: int = 10
    stochastic_noise_std: float = 0.1
    latency_jitter_threshold_std: float = 2.0
    venue_score_weights: Dict[str, float] = field(default_factory=lambda: {
        "depth": 0.4,
        "fill_rate": 0.4,
        "fees": 0.2
    })


@dataclass
class TrainingConfig:
    """Continuous training pipeline parameters."""
    validation_loss_tolerance: float = 0.02
    drawdown_penalty_weight: float = 3.0
    update_frequency: str = "daily"


@dataclass
class Config:
    """Master configuration container."""
    risk: RiskConfig = field(default_factory=RiskConfig)
    leverage: LeverageConfig = field(default_factory=LeverageConfig)
    hmm: HMMConfig = field(default_factory=HMMConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    
    # Capital and universe settings
    initial_capital: float = 1_000_000.0
    instrument_universe_size: int = 350
    
    @classmethod
    def load(cls, path: str) -> "Config":
        """Load configuration from YAML file.
        
        Args:
            path: Path to YAML configuration file
            
        Returns:
            Config instance with loaded parameters
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        return cls._from_dict(data)
    
    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Construct Config from dictionary."""
        config = cls()
        
        if "risk" in data:
            config.risk = RiskConfig(**data["risk"])
        if "leverage" in data:
            config.leverage = LeverageConfig(**data["leverage"])
        if "hmm" in data:
            hmm_data = data["hmm"].copy()
            thresholds = hmm_data.pop("regime_thresholds", {})
            config.hmm = HMMConfig(
                n_states=hmm_data.get("n_states", 3),
                regime_thresholds=thresholds
            )
        if "execution" in data:
            exec_data = data["execution"].copy()
            weights = exec_data.pop("venue_score_weights", {})
            config.execution = ExecutionConfig(
                twap_slices=exec_data.get("twap_slices", 10),
                stochastic_noise_std=exec_data.get("stochastic_noise_std", 0.1),
                latency_jitter_threshold_std=exec_data.get("latency_jitter_threshold_std", 2.0),
                venue_score_weights=weights
            )
        if "training" in data:
            config.training = TrainingConfig(**data["training"])
        if "initial_capital" in data:
            config.initial_capital = data["initial_capital"]
        if "instrument_universe_size" in data:
            config.instrument_universe_size = data["instrument_universe_size"]
        
        return config
    
    def validate(self) -> None:
        """Validate configuration parameters against constraints.
        
        Raises:
            ValueError: If any parameter violates hard constraints
        """
        if self.risk.max_daily_drawdown >= 0:
            raise ValueError("max_daily_drawdown must be negative")
        
        if self.risk.kelly_multiplier <= 0 or self.risk.kelly_multiplier > 1:
            raise ValueError("kelly_multiplier must be in (0, 1]")
        
        if self.risk.risk_per_trade <= 0 or self.risk.risk_per_trade > 0.1:
            raise ValueError("risk_per_trade must be in (0, 0.1]")
        
        if self.leverage.max_leverage < 1:
            raise ValueError("max_leverage must be >= 1")
        
        if self.hmm.n_states != 3:
            raise ValueError("HMM must have exactly 3 states (Low-Vol, High-Vol, Fractured)")
