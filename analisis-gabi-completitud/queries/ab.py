import random
random.seed(7)
N = 200_000

def beta_sample(a, b):
    return random.betavariate(a, b)

def test(nombre, s6, n6, s7, n7):
    d = []
    for _ in range(N):
        p6 = beta_sample(1 + s6, 1 + n6 - s6)
        p7 = beta_sample(1 + s7, 1 + n7 - s7)
        d.append(p7 - p6)
    d.sort()
    p_gana = sum(1 for x in d if x > 0) / N
    lo, hi = d[int(.025*N)], d[int(.975*N)]
    print(f"{nombre:<28} 1.0.6 {s6}/{n6} = {100*s6/n6:5.2f}%   "
          f"1.0.7 {s7}/{n7} = {100*s7/n7:5.2f}%   "
          f"lift {100*(s7/n7-s6/n6):+5.2f}pp  "
          f"IC95 [{100*lo:+5.2f}, {100*hi:+5.2f}]pp  P(1.0.7>1.0.6)={p_gana:.3f}")

print("=== OUTCOME BUENO (cita/visita/captado/cierre) ===")
test("TOTAL",            3557, 6087, 3597, 6122)
test("  estrato ibuyer",  477,  816,  499,  850)
test("  estrato null",    134, 2168,  151, 2144)
test("  estrato real_estate", 2946, 3103, 2947, 3126)
print()
print("=== NUNCA RESPONDIO (menor es mejor) ===")
test("TOTAL",             259, 6087,  254, 6122)
test("  estrato ibuyer",   18,  816,   12,  850)
test("  estrato null",    199, 2168,  201, 2144)
