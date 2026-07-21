"""Decisión bayesiana del A/B (Beta-Binomial), portada de marketing-loop-sellers/core/stats.py.
Misma metodología y umbrales que el motor (prob≥0.95, pérdida≤0.5pp, min 300/brazo, min 7d, tope 21d).
draws menor que el motor (40k) — suficiente para mostrar en el tablero, corre rápido en el build."""
import random
from math import comb

def analyze(succ_a, n_a, succ_b, n_b, prior=(1, 1), draws=40000, seed=0):
    rnd = random.Random(seed)
    aa, ba = prior[0] + succ_a, prior[1] + (n_a - succ_a)
    ab, bb = prior[0] + succ_b, prior[1] + (n_b - succ_b)
    wins = 0; loss_a = 0.0; loss_b = 0.0; diffs = []
    for _ in range(draws):
        ra = rnd.betavariate(aa, ba); rb = rnd.betavariate(ab, bb)
        if rb > ra: wins += 1
        loss_a += (rb - ra) if rb > ra else 0.0
        loss_b += (ra - rb) if ra > rb else 0.0
        diffs.append(rb - ra)
    diffs.sort()
    lo = diffs[int(0.025 * draws)]; hi = diffs[min(draws - 1, int(0.975 * draws))]
    return {"prob_b_beats_a": wins / draws,
            "expected_loss": {"choose_a": loss_a / draws, "choose_b": loss_b / draws},
            "ci_diff": (lo, hi)}

def decide(name_a, deliv_a, pos_a, name_b, deliv_b, pos_b, days_elapsed,
           min_per_arm=300, min_days=7, max_days=21, prob=0.95, eps=0.005, draws=40000, seed=0):
    res = analyze(pos_a, deliv_a, pos_b, deliv_b, draws=draws, seed=seed)
    p_b = res["prob_b_beats_a"]
    if p_b >= 0.5:
        winner, prob_w, loss_w = name_b, p_b, res["expected_loss"]["choose_b"]
    else:
        winner, prob_w, loss_w = name_a, 1 - p_b, res["expected_loss"]["choose_a"]
    base = {"winner": winner, "prob_winner": prob_w, "expected_loss_winner": loss_w}
    if deliv_a < min_per_arm or deliv_b < min_per_arm:
        return {**base, "decided": False, "reason": f"falta muestra (min {min_per_arm}/brazo)"}
    if days_elapsed < min_days:
        return {**base, "decided": False, "reason": f"faltan días (min {min_days})"}
    if prob_w >= prob and loss_w <= eps:
        return {**base, "decided": True, "reason": "señal decisiva"}
    if days_elapsed >= max_days:
        return {**base, "decided": True, "reason": "tope de días — gana el de mayor prob"}
    return {**base, "decided": False, "reason": "sin señal decisiva aún"}
