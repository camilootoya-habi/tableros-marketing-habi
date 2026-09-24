import random
random.seed(11); N = 200_000
def test(nombre, sA, nA, sB, nB):
    d = sorted(random.betavariate(1+sB, 1+nB-sB) - random.betavariate(1+sA, 1+nA-sA) for _ in range(N))
    p = sum(1 for x in d if x > 0)/N
    print(f"{nombre:<34} A {sA}/{nA}={100*sA/nA:5.1f}%   B {sB}/{nB}={100*sB/nB:5.1f}%   "
          f"dif {100*(sB/nB-sA/nA):+5.1f}pp  IC95 [{100*d[int(.025*N)]:+5.1f},{100*d[int(.975*N)]:+5.1f}]  P(B>A)={p:.3f}")
print("HANDOFF a etapa siguiente (gabi_mx O gabi_inmo_mx), 2026:")
test("  ibuyer",       628,  646, 1077, 1136)
test("  real_estate", 3820, 3894,  610,  620)
print("\nRESPONDIO al primer mensaje, 2026:")
test("  ibuyer",       463,  646, 1012, 1136)
test("  real_estate", 2850, 3894,  516,  620)
test("  sin_flag",    1996,10083, 2279, 7969)
