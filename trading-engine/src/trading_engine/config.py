"""
Configuration management for the trading engine.

Loads and validates configuration parameters from YAML files.
"""

import yaml
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class LeverageConfig:
    """Leverage configuration parameters."""
    max_gross: float = 10.0
    base: float = 1.0
    variance_premium_sensitivity: float = 0.5


@dataclass
class RiskConfig:
    """Risk management configuration."""
    daily_drawdown_limit: float = -0.025  # -2.5%
    risk_per_trade: float = 0.0075        # 0.75%
    kelly_multiplier: float = 0.40
    pre_emptive_deleveraging_threshold: float = 0.80


@dataclass
class RegimeConfig:
    """Regime classification configuration."""
    hmm_states: int = 3
    reestimate_frequency: str = "daily"
    state_names: tuple = ("Low-Vol/High-Liq", "High-Vol/Trending", "Fractured/Illiquid")


@dataclass
class ExecutionConfig:
    """Execution engine configuration."""
    twap_slices: int = 10
    latency_jitter_threshold: float = 2.0
    fee_crypto_bps: float = 2.0
    fee_equity_bps: float = 0.5
    fee_futures_bps: float = 0.3


@dataclass
class Config:
    """Main configuration container."""
    leverage: LeverageConfig = field(default_factory=LeverageConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    
    # System parameters
    instrument_universe_size: int = 350
    capacity_aum: float = 15_000_000  # $15M
    update_frequency_ms: int = 1
    
    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        leverage = LeverageConfig(**data.get('leverage', {}))
        risk = RiskConfig(**data.get('risk', {}))
        regime = RegimeConfig(**data.get('regime', {}))
        execution = ExecutionConfig(**data.get('execution', {}))
        
        return cls(
            leverage=leverage,
            risk=risk,
            regime=regime,
            execution=execution,
            **{k: v for k, v in data.items() 
               if k not in ['leverage', 'risk', 'regime', 'execution']}
        )
    
    @classmethod
    def default(cls) -> "Config":
        """Return default configuration."""
        return cls()
