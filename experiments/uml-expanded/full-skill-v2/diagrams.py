"""Full-folder skill workflows. Sources are resolved and bound by build.py."""

STYLE = """@startuml
!pragma useVerticalIf on
skinparam backgroundColor #FFFFFF
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam defaultFontSize 17
skinparam ArrowColor #46566F
skinparam activity {
  BackgroundColor #EEF5FF
  BorderColor #365A82
  FontColor #152B44
  DiamondBackgroundColor #FFF3D6
  DiamondBorderColor #BA842A
}
skinparam noteBackgroundColor #FFF8DE
skinparam noteBorderColor #BEA45C
skinparam wrapWidth 370
"""

DIAGRAMS = {
"llm-prefix-cache-replay": {
"prefix-cache-replay": r"""
title Prefix-cache replay | S3FIFO accounting and state transitions
start
if (Declared policy is S3FIFO?) then (yes)
else (other)
 :Follow the companion cache-policy-comparison\nworkflow for LRU/LFU/FIFO, with the same\nprefix accounting before accesses [S2];
 stop
endif
partition "Configuration and state [S1]" {
 :Read declared policy, block_size, capacity,\nsmall_ratio and max_freq; keep trace order;
 :For S3FIFO: S_cap = round(capacity * small_ratio);\nM_cap = capacity - S_cap; G_cap = M_cap;\nstart empty S, M and metadata-only G;
}
while (Another request?) is (yes)
 partition "1. Observe pre-request residency [S1]" {
  :Scan hashes from index 0; stop at first miss;\nresident means S union M, never G;\nhit_tokens = min(k * block_size, input_length);
 }
 partition "2. Access EVERY hash in order [S1]" {
  while (Another hash h?) is (yes)
   if (h resident in S or M?) then (yes)
    :Increment and saturate freq at max_freq;\nkeep FIFO position unchanged;
   elseif (h in G?) then (ghost)
    :Remove h from G; admit_M(h, 0);
   else (new)
    while (S full before admission?) is (yes)
     :Pop S head (v, vf);
     if (vf >= 1?) then (warm)
      :admit_M(v, vf); preserve frequency;
     else (cold)
      :insert_G(v);
     endif
    endwhile (space)
    :Append (h, 0) to S tail;
   endif
  endwhile (all accessed)
 }
 :Save per-request prompt/hit tokens;\naccumulate totals;
endwhile (end of trace)
:Check sums and hit-token cap;\nrate = total_hit / total_prompt;\nfinal_cache_blocks = size(S) + size(M);
stop
legend right
  S1 callable helper: admit_M(h, f)
  If full, inspect M head (v, vf):
  vf >= 1 -> pop, append (v, vf-1) to TAIL;
  repeat until vf=0 -> pop, insert_G(v), stop.
  Append (h, f). One permanent eviction per admission.

  S1 callable helper: insert_G(h)
  If present, remove h before re-append.
  Else, if full, discard oldest ghost.
  Append hash only; G is never resident.

  S1 invariants
  No re-tokenizing hash_ids. No set intersection.
  Count hits BEFORE applying any accesses.
  Keep promoted frequency; new/ghost admissions use 0.
endlegend
""",
"cache-policy-comparison": r"""
title Cache policies | distinct transitions, common measurement
start
:Read declared policy; give each policy\nits own empty state and identical capacity/trace [S1];
if (Declared policy?) then (LRU)
 :OrderedDict: hit -> move to tail;\nmiss -> append; overflow -> pop head [S1];
elseif (LFU?) then (yes)
 :Hit -> freq += 1; new key -> freq = 1;\nat capacity evict minimum frequency,\nthen oldest insertion as deterministic tie-break [S1];
elseif (FIFO?) then (yes)
 :Hit -> keep queue order; miss -> append;\noverflow -> pop oldest insertion [S1];
elseif (S3FIFO?) then (yes)
 :Use linked prefix-cache-replay algorithm [S2];\nS/M/G, saturated freq, second chance in M;\npreserve S-to-M freq; ghost hit admits to M at 0;
else (other)
 :Get the missing policy specification;\nARC is named but not implemented in this folder [S1];
 stop
endif
while (Another request?) is (yes)
 :Measure longest resident prefix BEFORE access;\ncap hit tokens at prompt length [S1, S2];
 :Access every hash in order using selected policy;\nkeep ghost metadata out of residency [S1, S2];
endwhile (no)
:Compare weighted hit rate, final residency,\nper-request distribution and admission effort [S1];
:Relate measurements to recency / hot-set /\nrandom workload; do not assume a winning policy [S1];
stop
""",
},
"energy-market-pricing": {
"power-flow-data": r"""
title Network data | schema, identifiers and units
start
:Parse the whole network JSON with json.load;\nprint dimensions and total active load only [S1];
note right
 S1: large networks should not be dumped
 line by line into the model context.
end note
:Load baseMVA, bus, gen, branch and gencost;\nread reserve_capacity / reserve_requirement\nwhen present in the declared input [S1];
:Build bus_number -> zero-based row mapping;\nmap every generator and branch endpoint [S1];
note right
 Bus labels may have gaps.
 Never substitute bus_id - 1.
end note
:Classify buses: slack=3, PV=2, PQ=1;\nlocate reference bus with angle zero [S1];
:Read branch R[2], X[3], charging[4],\nRATE_A[5] and in-service flag[10] [S1];
:Keep physical and per-unit values distinct;\nP_pu = P_MW / baseMVA;\nP_MW = P_pu * baseMVA [S1];
:Compute load = sum(bus[:,2]);\nreturn mapped arrays, topology, units\nand declared reserve fields [S1];
stop
""",
"dc-power-flow": r"""
title DC power flow | use the supplied helper implementation
start
:Use lossless lines, unit voltage magnitudes\nand small angle differences [S1];
partition "Build B with scripts/build_b_matrix.py [S2]" {
 :Call build_susceptance_matrix(branches, buses);\nbuild bus-ID mapping; initialize zero B;
 while (Another branch?) is (yes)
  :Map endpoints; read reactance x;
  if (x != 0?) then (yes)
   :b = 1/x; add b to B[f,f], B[t,t];\nsubtract b from B[f,t], B[t,f];
  else (zero)
   :b = 0; do not update B;
  endif
  :Append b to branch_susceptances\nin the original branch order;
 endwhile (done)
 :Return B, branch_susceptances, bus_num_to_idx;
}
if (Only matrix diagnostics needed?) then (yes)
 :CLI: python scripts/build_b_matrix.py network.json;\nreports matrix size, nonzero count, symmetry [S2];
else (DC model / OPF)
 :Add nodal balance Pg_pu - Pd_pu = B * theta;\nfix type-3 slack angle to zero [S1];
 :Apply line bounds in MW using saved b;\nsolve for theta in the surrounding model [S1];
 :Call calculate_line_flows(branches, saved_b,\ntheta, baseMVA, bus-ID mapping) [S2];
 :For every branch: flow_MW = b*(theta_f-theta_t)*baseMVA;\nlimit_MW = RATE_A; loading = abs(flow)/limit*100\nwhen limit > 0, otherwise 0 [S2];
 :Return original from/to bus IDs, flow_MW,\nlimit_MW and loading_pct [S2];
endif
stop
""",
"economic-dispatch": r"""
title Economic dispatch | cost reference plus reserve coupling
start
:Map generator buses; read Pmin[9], Pmax[8];\nPg is per-unit, P_MW = Pg * baseMVA [S1];
partition "Interpret each gencost row [S1, S2]" {
 if (MODEL = 2 polynomial?) then (yes)
  :Read NCOST and highest-order-first coefficients;\nquadratic: c2*P_MW^2 + c1*P_MW + c0;\nlinear / constant: use the matching coefficient count;
  note right
   S1's example treats NCOST >= 3 as quadratic.
   S2 documents the general polynomial layout.
   Check higher-degree data before reusing that example.
  end note
 else (not polynomial)
  if (MODEL = 1 piecewise linear?) then (yes)
   :Read N ordered (P,C) breakpoints from S2;\nuse the stated piecewise cost representation;\ndo not read these entries as polynomial coefficients;
  else (unsupported)
   :Resolve the cost representation before optimizing;
   stop
  endif
 endif
}
:Bound Pg by Pmin/baseMVA and Pmax/baseMVA [S1];
if (Network constraints included?) then (yes)
 :Use nodal DC balances and branch limits;\nsee the companion dc-power-flow skill [S1];
else (aggregate dispatch)
 :sum(Pg) = total_load_MW / baseMVA [S1];
endif
if (Reserves required?) then (yes)
 :Use Rg in MW; 0 <= Rg <= reserve_capacity;\nPg*baseMVA + Rg <= Pmax_MW;\nsum(Rg) >= reserve_requirement [S1];
endif
:Minimize total generation cost;\nGUIDE selects CLARABEL for quadratic network OPF [S1];
:Export generator ID, bus, Pg_MW and Pmax_MW;\nreport cost, load and generation; when reserves\nare modeled also report Rg_MW, reserve totals\nand headroom sum(Pmax-Pg_MW-Rg) [S1];
note right
 S2: polynomial marginal cost = 2*c2*P + c1.
 Cost uses MW; coefficient units must match.
end note
stop
""",
"locational-marginal-prices": r"""
title Locational prices | dual references and same-case comparisons
start
:Build DC-OPF and retain each bus balance\nconstraint plus the system reserve constraint [S1];
:Solve base case with CLARABEL;\nread duals after solving [S1];
:Associate each balance dual with its original bus ID;\ncheck constraint orientation and units\nbefore using the source's price convention [S1];
note right
 S1 sample: lmp = dual * baseMVA, or 0 if None.
 Verify sign and scaling against the actual
 balance equation and its power units.
 Label missing-dual fallbacks as such.
end note
:Read reserve requirement dual as reserve MCP;\ncompute flows and loading; mark lines only if\nx != 0, RATE_A > 0 and loading >= 99% [S1];
:Save base cost, all bus prices, binding lines\nand target-line binding state [S1];
:Find target line in either direction;\nchange its requested thermal rating only [S1];
:Re-solve counterfactual; extract prices, flows\nand binding lines with the same conventions [S1];
:Compute base_cost - cf_cost;\nfor each bus: delta = cf_LMP - base_LMP;\ncompare target binding before/after [S1];
:Check relaxation cannot increase optimal cost;\ninterpret price separation and congestion;\nnegative prices alone are not an error [S1];
stop
""",
},
"r2r-mpc-control": {
"state-space-linearization": r"""
title State-space linearization | operating point and discretization
start
:Specify nonlinear dx/dt=f(x,u), dimensions n,m\nand reference operating point (x_ref,u_ref) [S1];
:Evaluate A_c = df/dx and B_c = df/du\nat that operating point [S1];
note right
 S1 R2R partial derivatives:
 d(dT_i/dt)/dT_i = -v_i/L
 d(dT_i/dt)/dv_i = EA/L - T_i/L
 d(dv_i/dt)/dT_i = -R^2/J
 d(dv_i/dt)/du_i = R/J
end note
if (Discretization choice?) then (Euler)
 :A_d = I + dt*A_c; B_d = dt*B_c [S1];
else (matrix exponential)
 :A_d = expm(A_c*dt) [S1];
 if (A_c invertible for the supplied formula?) then (yes)
  :B_d = inv(A_c)*(A_d-I)*B_c [S1];
 else (no)
  :Do not evaluate an undefined inverse;\nrevisit the method / Euler option [S1 formula condition];
  stop
 endif
endif
:Check matrix dimensions and eigenvalues;\npass the discrete model to controller design [S1];
if (Operating point changes significantly?) then (yes)
 :Re-linearize around the updated reference [S1];
else (no)
 :Retain the current linearization [S1];
endif
stop
""",
"finite-horizon-lqr": r"""
title Finite-horizon LQR | backward pass inside receding-horizon control
start
:Supply A, B, Q, R and horizon N;\nchoose terminal P_N = Q or LQR terminal cost [S1];
while (Next control timestep?) is (yes)
 :Measure current x_0; reset P to P_N;\nset k = N-1 [S1];
 while (k >= 0?) is (yes)
  :K_k = solve(R + B' P B, B' P A);\nP_k = Q + A' P (A - B K_k);\nstore K_k, set P=P_k, decrement k [S1];
 endwhile (backward pass done)
 :Apply ONLY the first action u_0 = -K_0*x_0;\nadvance the plant / simulator one timestep [S1];
endwhile (finished)
:Return / log the applied controls and states [S1];
note right
 S1 objective: sum(x'Qx + u'Ru) + x_N' P_N x_N.
 Forward prediction uses x_next = A*x + B*u.
 Receding-horizon use measures again rather than
 applying the entire old predicted sequence.
end note
stop
""",
"mpc-horizon-tuning": r"""
title MPC tuning | select parameters, then evaluate a trial
start
partition "Parameter selection before a control trial [S1]" {
 :Choose horizon considering response and compute;\nGUIDE: N=5..15 typical for dt=0.01s;\nN<5 may reject disturbances poorly; N>20 costs more;
 note right
  S1 also gives N approx 2..3 * settling_time / dt.
  Treat these as context-dependent guidelines,
  not simultaneously enforced hard constraints.
 end note
 :Set Q tension weights 100/T_ref^2;\nvelocity weights 0.1/v_ref^2;\nR = (0.01..0.1)*I [S1];
 :Choose LQR terminal cost with consistent\ncontinuous/discrete model conventions [S1];
 note right
  S1 shows solve_continuous_are(A,B,Q,R).
  Check the supplied A,B convention before use.
 end note
}
:Run a trial with this fixed parameter choice;\nobserve tracking, effort and compute cost [S1];
if (Trial indicates retuning?) then (yes)
 :Plan the next trial: higher Q gives faster\ntracking / more effort; higher R gives smoother\ncontrol / slower response; reconsider N [S1];
else (no)
 :Retain selected N,Q,R and terminal cost [S1];
endif
stop
""",
"integral-action-design": r"""
title Integral action | separate trial tuning from timestep updates
start
partition "Choose a trial configuration [S1]" {
 :Choose dt, c_I, gamma and max_integral;\nstart c_I near 0.1..0.3; gamma commonly 0.9..0.99;
 :Initialize one integral term per tension section;
}
partition "Runtime loop with the chosen configuration [S1]" {
 while (Next control timestep?) is (yes)
  :Measure section tensions T and reference T_ref;
  :For each section:\nu_I = gamma*u_I - c_I*dt*(T-T_ref);
  :Clip u_I to [-max_integral,+max_integral];\nu_total = u_mpc + u_I;
  :Apply u_total and record the response;
 endwhile (trial finished)
}
partition "Review after the trial [S1]" {
 if (Offset correction too slow?) then (yes)
  :Consider higher c_I for a subsequent trial;
 elseif (Oscillatory / unstable?) then (yes)
  :Consider lower c_I; review decay and saturation;
 else (acceptable)
  :Retain configuration;
 endif
}
note right
 S1: gamma=1 is a pure integrator; gamma<1 leaks.
 c_I 0.1..0.5 is a stated web-system range.
 Tuning advice does not require changing gains
 inside every control timestep.
end note
stop
""",
},
"exam-block-sequencing": {
"mip-solver-and-solution-audit": r"""
title MIP execution | one incumbent, one disk artifact, one audit
start
partition "Discover and formulate [S1]" {
 :Test installed callable solvers; try importing\nPySCIPOpt first; use it if available unless\na clearly better supplied solver is appropriate;
 :If a solver-based integer program is required,\nuse heuristics only as allowed warm starts /\nimprovements, not a silent replacement;
 :Build integer/binary decisions, hard constraints,\nlinked auxiliaries and complete named objective;\nset the solve time limit before optimize();
}
:Optimize; capture status, incumbent,\nbest bound and gap when available [S1];
if (Feasible incumbent exists?) then (yes)
 :Select getBestSol(); extract via getSolVal(sol,var)\nor model.getVal(var), not var.getVal() [S1];
else (none)
 :Report no feasible solution and solver status;\ndo not fabricate outputs or a certificate [S1];
 stop
endif
:Validate extracted assignments, counts, uniqueness,\neligibility, timing, policy and finite values [S1];
if (Post-processing changes the incumbent?) then (yes)
 :Disclose the change; old gap / optimality\ncertificate does not automatically certify it [S1];
endif
partition "Final artifact is the source of truth [S1]" {
 :Write the chosen schedule / assignment to disk;
 :RELOAD that exact file; run a pure evaluator\nusing only input data plus the final artifact;
 :Recompute every component; compare to solver\nobjective when intended to match (tolerance 1e-6);\nfix model, semantics or extraction if inconsistent;
 :Write metrics and formulation/report from\nthis same audited solution;
 :Reload output again; rerun evaluator;\nrequire reported and disk-derived metrics to agree;
}
:State minimize/maximize, each item exactly once,\nposition/resource rules, pair/triple/overlap terms,\noptional constraints, variables/linking, solver,\ntime limit, status, incumbent, bound/gap and method [S1];
if (Optimality certified by status/gap?) then (yes)
 :Make only the supported certified claim [S1];
else (time limit / other)
 :Report a feasible incumbent and known gap;\nfeasible does not mean proven optimal [S1];
endif
stop
""",
"ordered-window-sequencing-mip": r"""
title Ordered windows | preserve sequence, masks and active overlaps
start
:Record ordered positions, successor relation,\nitems and required counts; keep tuple keys ordered;\ndefine missing-row meaning from supplied schema [S1];
note right
 Never sort tuple keys, add reverse pairs or
 sum all permutations without an explicit rule.
 Position labels need not be contiguous integers.
end note
if (Sequence representation?) then (assignment-linked)
 :Create assign[item,position]; enforce each item\nexactly as required and each required position filled;
 :For r-item windows create z for eligible starts;\nz <= each matching assign variable;\nz >= sum(assign variables) - (r-1) [S1];
else (direct ordered windows)
 :Create W[t,a1,...,ar]; one window per eligible start;\nrequired item-role counts; forbid repeats when\nrepresenting a permutation [S1];
 :Link adjacent windows: sum over leading item\nW[t,a0,q1,...] = sum over trailing item\nW[next(t),q1,...,ar] [S1];
endif
:Use cyclic continuity ONLY if explicitly defined;\nreporting masks may still exclude boundary starts [S1];
partition "Objective contract before optimization [S1]" {
 :For every component record ordered tuple offsets,\neligible-start mask, successor rule and weights;
 :Build active primitive patterns from those starts;
 :Define overlap via membership in the required\nactive patterns; attach its specified ordered cost;
 note right
  For binary pattern indicators A,B:
  overlap <= A; overlap <= B;
  overlap >= A+B-1.
  Active overlapping windows are NOT automatically
  all combinations inside a wider window.
 end note
 :Keep pair, triple and high-order overlap terms\ninside the minimized weighted objective;
}
:Solve and extract one global sequence;\napply independent evaluate(sequence,input) [S1];
:Audit ordering, masks, successor and boundary\nrules, missing tuples, overlaps and feasibility;\nhand the final artifact to solution-audit workflow [S1];
stop
""",
},
"manufacturing-fjsp-optimization": {
"fjsp-baseline-repair-with-downtime-and-policy": r"""
title FJSP baseline repair | commitments, integer scan and budgets
start
partition "Repair scope and input [S1, S2]" {
 :Restore baseline feasibility while limiting change;\nread eligible machines and machine-specific times,\ndowntime, baseline and change budgets;
 :Sort downtime; retain ORIGINAL machine/start\nfor MC and L1 accounting;
 :Sort operations by (op index, baseline start,\noriginal baseline list index) [S1];
}
while (Another operation in that order?) is (yes)
 :anchor = max(baseline start,\nnew end of previous operation of this job) [S1];
 :List only legal machines; try baseline machine first;\nif baseline machine illegal, choose a legal default\n(minimum duration is one stated heuristic) [S1];
 partition "Candidate timing for EACH considered machine [S1]" {
  :Use this machine's own duration; set t=anchor;
  while (Conflict with committed work or downtime?) is (yes)
   :Increment t by exactly 1; test again;
  endwhile (first feasible integer)
  :Candidate interval is [t,t+duration);
 }
 if (Large shift and change budget remains?) then (yes)
  :Consider legal alternates with the SAME scan;\nsource suggests accepting an earlier-start alternate [S1];
 endif
 :Choose using stated change/shift priorities\nand remaining MC/L1 budgets [S1];
 note right
  S1 gives both lexicographic machine-change-first
  scoring and an earlier-alternate trigger.
  These are heuristic suggestions: state a consistent
  priority rather than claiming both always agree.
 end note
 :Commit immediately in the SAME repair order;\nupdate machine intervals, predecessor end,\nMC and L1 totals [S1];
endwhile (done)
:Check legal machine/duration, precedence,\nno earlier-than-baseline starts, no overlap/downtime,\nMC/L1 budgets and makespan improvement [S1];
:Replay local placement in repair order: when\nstart > anchor, start-1 must be infeasible [S1];
note right
 Half-open overlap: s < b AND a < e.
 MC compares to ORIGINAL baseline machine.
 L1 = sum(abs(new_start - baseline_start)).
 The sample helper's safety-bound return alone
 is not a proof that the returned slot is feasible.
end note
:Return the repaired schedule and measured changes;
stop
legend bottom
 S2 shared reference.md: baseline repair preserves production commitments.
 FJSPLib provenance, difficulty labels and bibliography provide context;
 they do not supply a new repair algorithm or a task runtime budget.
endlegend
""",
},
}
