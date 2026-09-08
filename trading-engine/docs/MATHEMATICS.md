# Mathematical Foundations

This document provides the explicit mathematical formulations governing the core algorithmic components of the trading engine.

## 1. Avellaneda-Stoikov Market-Making Formulation

### Reservation Price

The reservation price serves as the anchor for the market-making agent's quotes:

$$r(s, q, t) = s - q \cdot \gamma \cdot \sigma^2 \cdot (T - t)$$

Where:
- $s$: Current mid-price
- $q$: Current inventory position
- $\gamma$: Risk-aversion parameter (default: 0.1)
- $\sigma^2$: Variance of the asset's returns
- $T$: Terminal time
- $t$: Current time

### Optimal Spread

The optimal bid-ask spread is calculated to balance execution probability against adverse selection:

$$\delta^* = \frac{1}{\gamma} \ln\left(1 + \frac{\gamma}{k}\right)$$

Where $k$ is the order arrival intensity parameter.

## 2. Proximal Policy Optimization (PPO) Objective

The meta-learner uses PPO to dynamically adjust capital allocation across agents:

$$L(\theta) = \mathbb{E}_t\left[\min\left(r_t(\theta) \cdot A_t, \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon) \cdot A_t\right)\right]$$

Where:
- $r_t(\theta) = \frac{\pi_\theta(a_t|s_t)}{\pi_{\theta_{old}}(a_t|s_t)}$: Probability ratio
- $A_t$: Estimated advantage function
- $\epsilon$: Clipping hyperparameter (typically 0.2)

### State Space

$$S_t = [\text{Sharpe}_{1:4}, P_{\text{regime}}, \text{VRP}, \text{Inventory}, \text{TimeEmbed}]$$

### Action Space

$$A_t = \text{softmax}(\text{logits}) \in \Delta^3$$

Constrained to simplex: $\sum w_i = 1, w_i \geq 0$

## 3. Fractional Kelly Criterion

Full Kelly fraction:

$$f^* = \frac{\mu}{\sigma^2}$$

Deployed fraction with estimation error correction:

$$f_{\text{deployed}} = \lambda \cdot \frac{\mu}{\sigma^2}$$

Where $\lambda = 0.40$ (fractional multiplier).

Subject to hard cap: $|f_{\text{deployed}}| \leq 0.75\%$

## 4. Dynamic Leverage Scaling via Variance Risk Premium

Variance Risk Premium definition:

$$\text{VRP}_t = \text{IV}_t^2 - \text{RV}_t^2$$

Target gross leverage:

$$L_t^* = \min\left(L_{\max}, L_{\text{base}} \cdot \left[1 + \alpha \cdot \frac{\text{VRP}_t}{\sigma_{\text{VRP}}}\right]\right)$$

Where:
- $L_{\max} = 10.0$: Leverage ceiling
- $L_{\text{base}} = 1.0$: Baseline leverage
- $\alpha = 0.5$: Sensitivity coefficient
- $\sigma_{\text{VRP}}$: Trailing standard deviation of VRP

## 5. Hidden Markov Model Regime Classification

### Transition Matrix

$$P(S_{t+1} = j | S_t = i) = A_{ij}$$

### Emission Probabilities (Gaussian)

$$P(O_t | S_t = i) = \mathcal{N}(O_t; \mu_i, \Sigma_i)$$

### Forward Algorithm

$$\alpha_t(i) = \left[\sum_j \alpha_{t-1}(j) A_{ji}\right] \cdot P(O_t | S_t = i)$$

### Posterior State Probabilities

$$P(S_t = i | O_{1:t}) = \frac{\alpha_t(i)}{\sum_j \alpha_t(j)}$$

## 6. Parkinson Volatility Estimator

$$\sigma^2 = \frac{1}{4 \ln 2} \left(\ln\frac{H}{L}\right)^2$$

Where $H$ and $L$ are high and low prices over the estimation window.

## 7. Ledoit-Wolf Shrinkage Estimator

For large-dimensional covariance matrix estimation:

$$\hat{\Sigma} = (1 - \delta) \cdot S + \delta \cdot F$$

Where:
- $S$: Sample covariance matrix
- $F$: Shrinkage target (typically identity or constant correlation)
- $\delta$: Optimal shrinkage intensity

## 8. Circuit Breaker Logic

Hard-stop trigger condition:

$$\text{Trigger} = \begin{cases} 
\text{True} & \text{if } \text{PnL}_{\text{daily}} \leq -2.5\% \\
\text{False} & \text{otherwise}
\end{cases}$$

Pre-emptive de-leveraging:

$$\text{Delever} = \begin{cases}
\text{True} & \text{if } \frac{\text{Margin}_{\text{required}}}{\text{Collateral}} \geq 80\% \\
\text{False} & \text{otherwise}
\end{cases}$$

## References

1. Avellaneda, M., & Stoikov, S. (2008). High-Frequency Trading in a Limit Order Book. *Quantitative Finance*.
2. Schulman, J., et al. (2017). Proximal Policy Optimization Algorithms. *arXiv*.
3. Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal*.
4. Parkinson, M. (1980). The Extreme Value Method for Estimating the Variance of the Rate of Return. *Journal of Business*.
5. Ledoit, O., & Wolf, M. (2004). A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices. *Journal of Multivariate Analysis*.
