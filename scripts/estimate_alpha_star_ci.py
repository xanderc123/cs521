"""Estimate empirical alpha* curves with confidence intervals.

Outputs:
  - results/alpha_star/pointwise_excess_stats.csv
  - results/alpha_star/alpha_star_by_gamma.csv
  - results/alpha_star/alpha_star_operational.csv
  - results/alpha_star/empirical_vs_analytical_alpha_star.png
  - results/alpha_star/excess_curves_by_gamma.png

Run:
  python scripts/estimate_alpha_star_ci.py --n-rounds 5000 --n-reps 200
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import time
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Ensure project root is importable even when run from scripts/ directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from selfish_mining_sim.engine import handle_event, run_simulation
from selfish_mining_sim.models import MiningEvent, SimState


ANALYTICAL_GAMMAS = [0.0, 0.25, 0.5, 0.75, 1.0]


@dataclass(frozen=True)
class MappingConfig:
    gamma0: float = 0.10
    w_latency: float = 0.60
    w_pool: float = 0.30


def analytical_alpha_star(gamma: float) -> float:
    if gamma >= 1:
        return 0.0
    return (1.0 - gamma) / (3.0 - 2.0 * gamma)


def ci95(values: np.ndarray) -> tuple[float, float, float]:
    mean = float(np.mean(values))
    if len(values) <= 1:
        return mean, mean, mean
    se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
    margin = 1.96 * se
    return mean, mean - margin, mean + margin


def gamma_eff(
    latency_edge: float, pool_size: float, cfg: MappingConfig
) -> float:
    g = cfg.gamma0 + cfg.w_latency * latency_edge + cfg.w_pool * pool_size
    return float(np.clip(g, 0.0, 1.0))


def simulate_excess_samples(
    alpha: float,
    gamma: float,
    n_rounds: int,
    n_reps: int,
    seed_base: int,
) -> np.ndarray:
    samples = np.empty(n_reps, dtype=float)
    for r in range(n_reps):
        import random

        random.seed(seed_base + r)
        # Fast path: avoid per-round DataFrame allocation inside run_simulation.
        state = SimState()
        for _ in range(n_rounds):
            event = (
                MiningEvent.SELFISH_FINDS
                if random.random() < alpha
                else MiningEvent.HONEST_FINDS
            )
            state = handle_event(state, event, gamma)
        samples[r] = state.revenue_selfish() - alpha
    return samples


def estimate_pointwise_stats(
    gammas: Iterable[float],
    alphas: np.ndarray,
    n_rounds: int,
    n_reps: int,
    seed: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    k = 0
    total_points = len(list(gammas)) * len(alphas)
    # Re-create iterator because len(list(...)) consumed it if not a list.
    gammas = list(gammas)
    total_points = len(gammas) * len(alphas)
    t0 = time.time()
    for gamma in gammas:
        print(f"[gamma={gamma:.2f}] starting alpha sweep...")
        for alpha in alphas:
            seed_base = seed + 100000 * k
            excess = simulate_excess_samples(
                alpha=float(alpha),
                gamma=float(gamma),
                n_rounds=n_rounds,
                n_reps=n_reps,
                seed_base=seed_base,
            )
            mu, lo, hi = ci95(excess)
            rows.append(
                {
                    "gamma": float(gamma),
                    "alpha": float(alpha),
                    "mean_excess": mu,
                    "ci95_low_excess": lo,
                    "ci95_high_excess": hi,
                    "n_reps": int(n_reps),
                    "n_rounds": int(n_rounds),
                }
            )
            k += 1
            if k % 10 == 0 or k == total_points:
                elapsed = time.time() - t0
                print(
                    f"  progress: {k}/{total_points} points "
                    f"({100.0*k/total_points:.1f}%), elapsed={elapsed/60:.1f} min"
                )
    return pd.DataFrame(rows)


def empirical_alpha_star_from_df(df_gamma: pd.DataFrame) -> float:
    candidate = df_gamma[df_gamma["ci95_low_excess"] > 0.0].sort_values("alpha")
    if candidate.empty:
        return np.nan
    return float(candidate.iloc[0]["alpha"])


def bootstrap_alpha_star_ci(
    gamma: float,
    alphas: np.ndarray,
    n_rounds: int,
    n_reps: int,
    seed: int,
    n_bootstrap: int = 300,
) -> tuple[float, float]:
    # Precompute per-alpha replicate-level samples once, then bootstrap on reps.
    per_alpha: dict[float, np.ndarray] = {}
    for i, alpha in enumerate(alphas):
        per_alpha[float(alpha)] = simulate_excess_samples(
            alpha=float(alpha),
            gamma=float(gamma),
            n_rounds=n_rounds,
            n_reps=n_reps,
            seed_base=seed + 500000 + i * 1000,
        )

    rng = np.random.default_rng(seed + 999999)
    boots = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n_reps, size=n_reps)
        rows = []
        for alpha in alphas:
            vals = per_alpha[float(alpha)][idx]
            mu, lo, hi = ci95(vals)
            rows.append(
                {
                    "alpha": float(alpha),
                    "mean_excess": mu,
                    "ci95_low_excess": lo,
                    "ci95_high_excess": hi,
                }
            )
        d = pd.DataFrame(rows)
        a_star_hat = empirical_alpha_star_from_df(d)
        if not np.isnan(a_star_hat):
            boots.append(a_star_hat)

    if not boots:
        return (np.nan, np.nan)
    low = float(np.quantile(boots, 0.025))
    high = float(np.quantile(boots, 0.975))
    return low, high


def plot_alpha_star_comparison(df_astar: pd.DataFrame, out_path: Path) -> None:
    plt.figure(figsize=(8, 5))
    plt.plot(
        df_astar["gamma"],
        df_astar["alpha_star_analytical"],
        "--",
        label="Analytical α*",
        linewidth=2.0,
    )
    plt.errorbar(
        df_astar["gamma"],
        df_astar["alpha_star_empirical"],
        yerr=[
            df_astar["alpha_star_empirical"] - df_astar["alpha_star_ci_low"],
            df_astar["alpha_star_ci_high"] - df_astar["alpha_star_empirical"],
        ],
        fmt="o-",
        capsize=4,
        label="Empirical α* (95% CI)",
    )
    plt.xlabel("γ")
    plt.ylabel("α*")
    plt.title("Empirical vs Analytical α*")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def plot_excess_curves(df_stats: pd.DataFrame, out_path: Path) -> None:
    plt.figure(figsize=(9, 6))
    for gamma in sorted(df_stats["gamma"].unique()):
        d = df_stats[df_stats["gamma"] == gamma].sort_values("alpha")
        x = d["alpha"].to_numpy()
        y = d["mean_excess"].to_numpy()
        lo = d["ci95_low_excess"].to_numpy()
        hi = d["ci95_high_excess"].to_numpy()
        plt.plot(x, y, label=f"γ={gamma:g}")
        plt.fill_between(x, lo, hi, alpha=0.15)
    plt.axhline(0.0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("α")
    plt.ylabel("Excess revenue: R_hat - α")
    plt.title("Pointwise excess curves with 95% CI")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def run_operational_sweep(
    alphas: np.ndarray,
    latency_edges: list[float],
    pool_sizes: list[float],
    cfg: MappingConfig,
    n_rounds: int,
    n_reps: int,
    seed: int,
) -> pd.DataFrame:
    rows = []
    combo_id = 0
    for latency_edge in latency_edges:
        for pool_size in pool_sizes:
            gamma = gamma_eff(latency_edge, pool_size, cfg)
            df_stats = estimate_pointwise_stats(
                gammas=[gamma],
                alphas=alphas,
                n_rounds=n_rounds,
                n_reps=n_reps,
                seed=seed + combo_id * 1000000,
            )
            a_star_emp = empirical_alpha_star_from_df(df_stats)
            a_star_ana = analytical_alpha_star(gamma)
            rows.append(
                {
                    "latency_edge": latency_edge,
                    "pool_size": pool_size,
                    "gamma_eff": gamma,
                    "alpha_star_empirical": a_star_emp,
                    "alpha_star_analytical": a_star_ana,
                }
            )
            combo_id += 1
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-rounds", type=int, default=5000)
    parser.add_argument("--n-reps", type=int, default=200)
    parser.add_argument("--alpha-min", type=float, default=0.05)
    parser.add_argument("--alpha-max", type=float, default=0.49)
    parser.add_argument("--alpha-step", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=521)
    parser.add_argument("--n-bootstrap", type=int, default=300)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_dir = root / "results" / "alpha_star"
    out_dir.mkdir(parents=True, exist_ok=True)

    alphas = np.round(
        np.arange(args.alpha_min, args.alpha_max + 1e-12, args.alpha_step), 4
    )

    print("Estimating pointwise excess curves...")
    df_stats = estimate_pointwise_stats(
        gammas=ANALYTICAL_GAMMAS,
        alphas=alphas,
        n_rounds=args.n_rounds,
        n_reps=args.n_reps,
        seed=args.seed,
    )
    df_stats.to_csv(out_dir / "pointwise_excess_stats.csv", index=False)

    print("Estimating empirical alpha* and CI by gamma...")
    rows = []
    for gamma in ANALYTICAL_GAMMAS:
        d = df_stats[df_stats["gamma"] == gamma].sort_values("alpha")
        a_emp = empirical_alpha_star_from_df(d)
        a_ana = analytical_alpha_star(gamma)
        lo, hi = bootstrap_alpha_star_ci(
            gamma=gamma,
            alphas=alphas,
            n_rounds=args.n_rounds,
            n_reps=args.n_reps,
            seed=args.seed + int(gamma * 1000) + 42,
            n_bootstrap=args.n_bootstrap,
        )
        rows.append(
            {
                "gamma": gamma,
                "alpha_star_empirical": a_emp,
                "alpha_star_ci_low": lo,
                "alpha_star_ci_high": hi,
                "alpha_star_analytical": a_ana,
                "abs_error": np.nan if np.isnan(a_emp) else abs(a_emp - a_ana),
            }
        )
    df_astar = pd.DataFrame(rows)
    df_astar.to_csv(out_dir / "alpha_star_by_gamma.csv", index=False)

    print("Running operational sweep (latency_edge, pool_size)...")
    cfg = MappingConfig()
    latency_edges = [0.0, 0.25, 0.5, 0.75, 1.0]
    pool_sizes = [0.05, 0.10, 0.20, 0.30, 0.40]
    df_ops = run_operational_sweep(
        alphas=alphas,
        latency_edges=latency_edges,
        pool_sizes=pool_sizes,
        cfg=cfg,
        n_rounds=args.n_rounds,
        n_reps=max(80, args.n_reps // 2),  # lighter default for expanded sweep
        seed=args.seed + 7000000,
    )
    df_ops.to_csv(out_dir / "alpha_star_operational.csv", index=False)

    print("Saving plots...")
    plot_alpha_star_comparison(
        df_astar, out_dir / "empirical_vs_analytical_alpha_star.png"
    )
    plot_excess_curves(df_stats, out_dir / "excess_curves_by_gamma.png")

    summary_path = out_dir / "README_experiment_notes.txt"
    summary_path.write_text(
        (
            "Empirical alpha* estimation summary\n"
            "=================================\n"
            f"n_rounds={args.n_rounds}, n_reps={args.n_reps}, n_bootstrap={args.n_bootstrap}\n"
            "gamma set: {0, 0.25, 0.5, 0.75, 1}\n\n"
            "Empirical alpha* definition:\n"
            "  smallest alpha where CI95 lower bound of (R_hat - alpha) > 0.\n\n"
            "Operational mapping:\n"
            "  gamma_eff = clip(gamma0 + w_latency*latency_edge + w_pool*pool_size, 0, 1)\n"
            f"  gamma0={cfg.gamma0}, w_latency={cfg.w_latency}, w_pool={cfg.w_pool}\n"
        ),
        encoding="utf-8",
    )

    print(f"Done. Outputs written to: {out_dir}")


if __name__ == "__main__":
    main()

