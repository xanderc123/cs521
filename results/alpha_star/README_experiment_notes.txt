Empirical alpha* estimation summary
=================================
n_rounds=2000, n_reps=100, n_bootstrap=150
gamma set: {0, 0.25, 0.5, 0.75, 1}

Empirical alpha* definition:
  smallest alpha where CI95 lower bound of (R_hat - alpha) > 0.

Operational mapping:
  gamma_eff = clip(gamma0 + w_latency*latency_edge + w_pool*pool_size, 0, 1)
  gamma0=0.1, w_latency=0.6, w_pool=0.3
