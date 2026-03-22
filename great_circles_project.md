# Wettest / Driest Great Circles — Project Notes

**Original conversation:** https://claude.ai/chat/113925b5-5856-4759-a09e-dca99636beea  
**Date:** March 2026

---

## Problem Definition

Find the great circle around Earth that:
- **Maximises** ocean/lake surface coverage ("wettest")
- **Minimises** ocean/lake surface coverage ("driest")

"Wettest" and "driest" refer purely to binary land/water coverage — not precipitation.

### Related prior work
Chabukswar & Mukherjee (2018) found the *longest uninterrupted* great-circle path over water (32,090 km, Pakistan → Kamchatka). That circle is a strong candidate for wettest, but their objective was longest segment, not maximum total ocean fraction. No one appears to have published the total-fraction version.

---

## Parameterisation (agreed)

A great circle is uniquely identified by its plane normal vector. Represent the normal as a point on the unit sphere:

- **Θ** (colatitude) ∈ [0°, 180°]  
- **Φ** (longitude) ∈ [0°, 180°)  — antipodal symmetry halves the range

Grid must be **sin(Θ)-weighted** to sample great circles uniformly (analogous to the solid-angle problem on a sphere). A naive uniform grid in (Θ, Φ) oversamples near the poles of the normal-vector space.

---

## Agreed implementation plan

| Item | Decision |
|------|----------|
| Primary data | ETOPO1 or GEBCO; elevation ≤ 0 → water |
| Lakes flag | Implement later; pre-rasterise HydroLAKES/GSHHG onto same grid |
| Search strategy | Coarse grid first (~1° steps → ~32,400 circles), then fine zoom |
| Samples per circle | ~3,600 points (0.1° spacing) |
| Implementation | Single Python script, NumPy + rasterio/netCDF4, WSL |
| Output (v1) | Print top results to console; visualisation later |

---

## Optimisation approaches discussed

The function f(Θ, Φ) = ocean fraction is smooth and likely not very spiky.

| Approach | Notes |
|----------|-------|
| Brute-force grid (coarse→fine) | Agreed starting point; simple, parallelisable; no optimality certificate |
| Gradient-based | Gets trapped in local optima; only useful from a good starting point |
| Basin-hopping / multistart | Better for non-convex; probably overkill |
| Branch and bound | Gives optimality certificate; doable but is a real mathematical project |

**Decision:** grid-first, then assess whether branch-and-bound rigour is needed.

---

## ⚠️ Unresolved objections

David noted unresolved objections to parts of the plan before the session ended. These were **not documented** — revisit the full conversation at the URL above before starting implementation.

---

## Environment

- Python in WSL2 on Windows laptop
- Claude Code CLI available
