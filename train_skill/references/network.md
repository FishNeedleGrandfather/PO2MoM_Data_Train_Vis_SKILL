# V7 network contract

Source of truth: `PO2MoM_TF/trainV7A.py`, classes `MLP`, `LocalExchange`, `BiasTransformerBlock`, `CoupleExchange`, `DownBlock`, `MGTransformer`, `Geo_cache`, `PO2MoMModel`. The class bodies in `trainV7AllAngle.py` are currently the same. Recheck after changes. `d=256`, eight attention heads, forward default `MG_NUM=4`. Complex vectors use interleaved real/imag pairs: `[Jx.re,Jx.im,Jy.re,Jy.im,Jz.re,Jz.im]`.

## Inputs and entrance

For `N0` triangles, `sample['X']` is `[N0,13]`: center `[N0,3]`, unit normal `[N0,3]`, area `[N0,1]`, normalized PO current `[N0,6]`. `Y` is `[N0,6]`; `K0` is scalar and `k_hat` is `[3]`. `cluster['c01']` maps each G0 triangle to G1 (`[N0]`); `cluster['c12']` maps G1 to G2 (`[N1]`). `geo_edges['e0'/'e1'/'e2']` and `cpl_edges['e1'/'e2']` are undirected edge tables `[2,E]`, expanded into two directions in the cache. Indices must match the current mesh, and G1/G2 clusters must be nonempty because area and averaged normal are divided by their magnitudes.

`POencoder` is MLP `6→128→128→256`, giving `h:[N0,256]`. Source features are `[k_hat(3), k_hat⊗normal(9), cos(K0 center·k_hat), sin(...)]`, total `[N0,14]`. `source_encoder` is `14→128→128→512`; split its output into `gamma,beta:[N0,256]`, then `h = h + h*gamma + beta`. The 10D geometry feature is center(3), normal(3), area(1), and mean neighbor normal-change at G0/G1/G2 (one each), where coarse changes are broadcast back through `c12` and `c01`. `geo_reader` is `10→128→128→512`, with the same gamma/beta injection applied after source injection. Both final MLP layers are zero-initialized so these injections initially act as identity in a fresh model. They are injected once, before graph exchange.

## Graph exchange and coarse return

`Geo_cache` computes once per forward: bidirectional G0 edge displacement `rho:[2E0,3]`, distance `[2E0,1]`, destination degree `[N0,1]`; area-weighted G1/G2 centers/areas/normals; bidirectional coupling endpoints; complex Green values `[2E1,2]`/`[2E2,2]`; and Green-gradient real/imag vectors `m1:[2E1,6]`, `m2:[2E2,6]`. Geometry-dependent operations are recomputed for each sample, but are shared across the four MG calls within that forward. Distances must be nonzero to avoid division by zero in Green calculations.

`LocalExchange` applies Pre-Norm to `h`, builds each directed edge input `[h_dst(256),h_src(256),rho(3),K0·distance(1)]` = 516D, sends it through an MLP to 256D, sums at destinations and divides by degree, then updates by MLP on `[h_norm,mean_message]` = 512D with residual `h + update`. One G0 block is called before MG; a *different* `local_exchange_post` module is called after every MG call, with parameters shared across those repetitions.

Inside one `MGTransformer`, aggregate G0→G1 using `sum(h*area)/area_g1`, yielding `[N1,256]`. At G1, `BiasTransformerBlock` does full self-attention on `[1,N1,256]` with `[8,N1,N1]` additive attention mask: an MLP maps complex Green `[2E1,2]` to eight edge biases, multiplied by learned `alpha` initialized to 0.1. Unspecified pairs have zero bias, so this is *not* a sparse attention mask. Its attention and 256→1024→256 FFN have Pre-Norm residuals. Parallel `CoupleExchange` multiplies source features `[2E1,256]` by Green-gradient components `[2E1,6]`, flattens to 1536D, maps to 256D, scales by source G1 area, and sums at destinations. Add transformer and coupling outputs.

Aggregate G1→G2 with G1 area weighting, then apply separate G2 bias-transformer and coupling modules in the same fashion. `DownBlock` G2→G1 and then G1→G0 uses normalized fine queries against all normalized coarse keys/values (dense cross-attention), gathers each fine node's parent, concatenates fine/context/parent to 768D, and computes `fine + sigmoid(gate)*update`; then adds a 256→1024→256 FFN. Gate weight is zero-initialized and bias −2 (initial gate ≈0.12). Returned fine sizes are `[N1,256]` then `[N0,256]`.

The MG module is a single object called four times by default, followed each time by the shared post-G0 exchange. Decoder MLP `256→128→128→6` yields `[N0,6]`. Reshape to `[N0,3,2]`, subtract the normal component independently for real and imaginary channels, and flatten back to `[N0,6]`. The output is only a correction; reconstruct current as `(X[:,7:13] + delta)*scale`.

## Implementation constraints

- Dense G1 attention scales quadratically in `N1`; large meshes such as SLICY may need workstation GPU memory planning. Altering this block changes checkpoint compatibility.
- `CoupleExchange` expects bidirectional `src,dst,m` to correspond, while `edges.size(1)` merely guards the empty-edge case. Preserve that alignment.
- The cache's coarse normals and Green values are physically determined by mesh/`K0`; changing edge orientation, cluster indexing, or normalization silently changes learned behavior.
- `BiasTransformerBlock.forward` accepts `k0`, but the current block uses Green values already computed with `K0`; avoid double-applying phase when adapting.
