#!/usr/bin/env python3
"""Skill-only activity diagrams. No task solutions or verifier data are inputs."""

from study import HERE

STYLE = """@startuml
!pragma useVerticalIf on
skinparam backgroundColor #FFFFFF
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam defaultFontSize 18
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
skinparam wrapWidth 360
"""

DIAGRAMS = {
"llm-prefix-cache-replay": {
"prefix-cache-replay": r"""
title Prefix cache replay - request accounting and S3FIFO
start
:Read block_size, capacity, small_ratio, max_freq;\nS_cap = round(capacity * small_ratio);\nM_cap = capacity - S_cap; G_cap = M_cap;
:Initialize empty FIFO queues S, M, G;\nresident = S union M; ghost is metadata only;
while (More requests in trace order?) is (yes)
  :Use residency BEFORE this request;\nscan hash_ids from index 0, stop at first miss;\nhit_tokens = min(k * block_size, input_length);
  while (More hashes in this request?) is (yes)
    :Take next hash h;
    if (h in S or M?) then (resident)
      :freq[h] = min(freq[h] + 1, max_freq);\nDo not reorder FIFO queues on a hit;
    else (not resident)
      if (h in G?) then (ghost hit)
        :Remove h from G;\nadmit_M(h, freq=0);
      else (new)
        while (S is full?) is (yes)
          :Pop head (victim, vf) from S;
          if (vf >= 1?) then (warm)
            :admit_M(victim, vf);\nPRESERVE the promoted frequency;
          else (cold)
            :insert_G(victim);
          endif
        endwhile (space)
        :Append h to S tail with freq=0;
      endif
    endif
  endwhile (all hashes accessed)
  :Append per-request accounting;\naccumulate prompt and hit totals;
endwhile (no)
:Report total_hit / total_prompt;\nfinal_cache_blocks = size(S) + size(M);\ncheck per-request sums; exclude G;
stop
legend right
  admit_M(h, f)
  While M is full, inspect its head (v, vf).
  vf >= 1: pop; decrement; append to TAIL; repeat.
  vf == 0: pop; insert_G(v); stop draining.
  Then append (h, f) to M tail.

  insert_G(h)
  Existing ghost: remove before re-appending.
  Otherwise, if full: pop oldest ghost.
  Append h; retain hashes only, no payload.

  Count hits BEFORE accesses; access EVERY hash.
  Never replace prefix scan with set intersection.
endlegend
""",
"cache-policy-comparison": r"""
title Cache policy comparison - preserve each policy's state rules
start
:Read declared policy and common capacity;\nuse identical trace and request accounting;
if (Policy?) then (LRU)
  :OrderedDict; on hit move key to tail;\non miss append; evict head if over capacity;
elseif (LFU?) then (yes)
  :Increment frequency on hit;\nevict minimum frequency on admission;\nbreak ties by oldest insertion order;
elseif (FIFO?) then (yes)
  :Append on admission; evict queue head;\non hit do NOT change insertion order;
else (S3FIFO)
  :Use prefix-cache-replay's full algorithm;\nS / M / G + saturated frequency;\nM uses second chance; G is nonresident;
endif
:For each request: inspect pre-access residency;\nthen apply all policy access side effects;
:Replay the same trace separately per policy;\nreport token-weighted hit rate, final residency,\nper-request distribution, admission effort;
:Check ghost exclusion and frequency bounds;\nmeasure workload behavior; do not assume a winner;
stop
""",
},
"energy-market-pricing": {
"power-flow-data": r"""
title Power-flow data - parse, map, normalize
start
:Parse network JSON with json.load;\ninspect array sizes and total active load;
note right
  Large files: summarize with Python.
  Do not dump line-by-line into context.
end note
:Read baseMVA, bus, gen, branch, gencost;\nread reserve_capacity and reserve_requirement;
:Build bus_number -> zero-based row mapping;\nmap generator buses and branch endpoints;
note right
  IDs may be non-contiguous.
  Never substitute bus_id - 1.
end note
:Classify buses: slack=3, PV=2, PQ=1;\nfind the slack reference bus;
:Interpret branch R, X, charging, RATE_A,\nand in-service flag from documented columns;
:Convert power units explicitly;\nP_pu = P_MW / baseMVA;\nP_MW = P_pu * baseMVA;
:Return mapped topology, power and reserve data;\ncheck total load using bus column 2;
stop
""",
"dc-power-flow": r"""
title DC power flow - nodal model and branch limits
start
:Use DC assumptions: lossless lines,\nunit voltage magnitudes, small angle differences;
:Build bus_number -> row mapping;\ninitialize B = zeros(n_bus, n_bus);
while (More branches?) is (yes)
  :Map from/to buses; read reactance x;
  if (x != 0?) then (yes)
    :b = 1/x;\nB[f,f] += b; B[t,t] += b;\nB[f,t] -= b; B[t,f] -= b;
  else (no)
    :Keep the guide's zero-susceptance handling;
  endif
endwhile (no)
:Add per-bus balance in per-unit:\nPg_at_bus - Pd = B[row,:] * theta;
:Find slack bus by type 3; fix theta_slack = 0;
:For each line, compute\nflow_MW = (theta_f - theta_t) / x * baseMVA;
:Enforce -RATE_A <= flow_MW <= RATE_A;\nloading_pct = abs(flow_MW) / RATE_A * 100;
:Return nodal constraints, line flows and loading;\nretain consistent MW / per-unit conversions;
stop
""",
"economic-dispatch": r"""
title Economic dispatch - costs, reserves, capacity coupling
start
:Read mapped generators and gencost;\nPg variables in per-unit; use Pg_MW = Pg * baseMVA;
while (More generator cost rows?) is (yes)
  :Read NCOST and polynomial coefficients;
  if (NCOST >= 3?) then (quadratic)
    :Add c2 * Pg_MW^2 + c1 * Pg_MW + c0;
  elseif (NCOST == 2?) then (linear)
    :Add c1 * Pg_MW + c0;
  else (constant)
    :Use the guide's constant / empty cost handling;
  endif
endwhile (no)
:Add Pmin / baseMVA <= Pg <= Pmax / baseMVA;
if (Network modeled?) then (yes)
  :Use nodal DC balance constraints;
else (aggregate)
  :Require sum(Pg) = total_load / baseMVA;
endif
if (Operating reserves required?) then (yes)
  :Add Rg in MW;\n0 <= Rg <= reserve_capacity;\nPg_MW + Rg <= Pmax_MW;\nsum(Rg) >= reserve_requirement;
endif
:Minimize generation cost;\nuse CLARABEL for quadratic network problems;
:Convert Pg back to MW; reserves remain MW;\nreport dispatch, cost, generation and reserve totals;
:Headroom = sum(Pmax_MW - Pg_MW - Rg_MW);
stop
""",
"locational-marginal-prices": r"""
title Locational prices - stored duals and counterfactual comparison
start
:Build DC-OPF; retain references to each\nnodal balance constraint and reserve requirement;
:Solve base case with CLARABEL;
:Read nodal duals; apply GUIDE's sign /\nbaseMVA convention; record all bus IDs and prices;
note right
  Complete GUIDE remains authoritative.
  This diagram preserves its workflow;
  it does not correct its equations.
  Negative prices can be physically valid.
end note
:Read reserve-constraint dual for reserve MCP;
:Compute line flows in MW;\ninclude lines with positive rating and >=99% loading;
:Save base costs, LMPs and binding lines;
:Locate the chosen line in either orientation;\nrelax only its thermal rating as requested;
:Re-solve the counterfactual model;\nextract costs, LMPs and binding lines the same way;
:Compute base_cost - counterfactual_cost;\ncompute per-bus delta = counterfactual - base LMP;
:Compare target-line binding state and price changes;\ncheck cost cannot increase when only a constraint relaxes;
stop
""",
},
"r2r-mpc-control": {
"state-space-linearization": r"""
title State-space linearization - operating point to discrete model
start
:Identify nonlinear dx/dt = f(x,u);\nchoose reference operating point (x_ref, u_ref);
:Compute Jacobians at the reference:\nA_c = df/dx (n by n); B_c = df/du (n by m);
:For R2R: include tension / velocity coupling\nand motor-torque terms from GUIDE;
if (Discretization method?) then (Euler)
  :A_d = I + dt * A_c;\nB_d = dt * B_c;
else (matrix exponential)
  :A_d = expm(A_c * dt);\nuse GUIDE's B_d expression and its\ninvertibility requirement for A_c;
endif
:Inspect eigenvalues and model stability;
if (Operating point changed significantly?) then (yes)
  :Update reference and re-linearize;
else (no)
  :Use A_d and B_d in discrete controller design;
endif
stop
""",
"finite-horizon-lqr": r"""
title Finite-horizon LQR - backward gains, first control, repeat
start
:Supply A, B, Q, R and horizon N;\nterminal P_N = Q or LQR terminal solution;
while (Next control timestep?) is (yes)
  :Measure current state x;\nset P = terminal cost;
  :Set k = N - 1;
  while (k >= 0?) is (yes)
    :K_k = solve(R + B' P B, B' P A);\nP = Q + A' P (A - B K_k);
    :Store K_k; decrement k;
  endwhile (backward pass done)
  :Apply ONLY u_0 = -K_0 * x;
  :Advance system / simulator one timestep;\nmeasure again and solve the shifted horizon;
endwhile (finished)
stop
""",
"integral-action-design": r"""
title Integral action - offset correction with anti-windup
start
:Initialize an integral term per tension section;\nchoose dt, integral gain c_I and decay gamma;
note right
  GUIDE ranges: c_I starts around 0.1-0.3;
  gamma commonly 0.9-0.99.
  gamma=1 is a pure integrator.
end note
while (Next control timestep?) is (yes)
  :Measure T and reference T_ref;
  :For each section:\nu_I = gamma*u_I - c_I*dt*(T - T_ref);
  :Clip u_I to [-max_integral, +max_integral];
  :Combine u_total = u_mpc + u_I;\napply control and observe tracking;
  if (Correction too slow?) then (yes)
    :Review integral gain; increase cautiously;
  elseif (Oscillation / instability?) then (yes)
    :Reduce gain; review decay and saturation;
  endif
endwhile (finished)
stop
""",
"mpc-horizon-tuning": r"""
title MPC tuning - balance tracking and control effort
start
:Choose timestep and initial horizon;\nGUIDE suggests N=5-15 for dt=0.01 s;
:Set diagonal Q with tension emphasis;\nQ_tension = 100 / T_ref^2;\nQ_velocity = 0.1 / v_ref^2;
:Set positive R for actuator effort;\nGUIDE example: 0.01-0.1 times identity;
:Choose terminal cost from LQR solution\nusing the model/time convention in GUIDE;
:Run controller and inspect response and computation;
if (Poor disturbance rejection?) then (yes)
  :Review a horizon that is too short;\nconsider larger N and tracking weight;
elseif (Computation too expensive?) then (yes)
  :Review excessive horizon length;
endif
if (Control too aggressive?) then (yes)
  :Increase R / reduce tracking emphasis;\nexpect slower response and more tracking error;
else (tracking needs faster response)
  :Increase Q or lower R cautiously;\nexpect higher effort and stronger transients;
endif
:Retest the tracking / effort / runtime trade-off;
stop
""",
},
"exam-block-sequencing": {
"ordered-window-sequencing-mip": r"""
title Ordered-window sequencing - objective semantics before optimization
start
:Read ordered positions, items and cost tables;\nbuild successor map from declared position order;
:Define tuple direction, eligible starts,\nboundaries and missing-row meaning;
note right
  Do not sort or symmetrize ordered tuples.
  Do not add reverse pairs or all permutations.
  Position labels need not be contiguous integers.
end note
if (Primary representation?) then (assignment-linked)
  :Create assign[item,position];\nadd pair / triple / window indicators;\nlink with ALL upper and lower bounds;
else (direct ordered windows)
  :Create W[start,ordered_tuple];\nchoose windows and link adjacent suffix / prefix;
endif
:Add each-item and each-position requirements;\nblock repeats and ineligible placements;
if (Overlap penalty present?) then (yes)
  :Define primitive active patterns and start mask;\nlink overlap indicators to both active patterns;\nkeep overlap costs IN the optimized objective;
  note right
    Active adjacent patterns and all triples
    inside a four-slot span are different rules.
    Use the instance's declared semantics.
  end note
endif
:Handle boundaries explicitly; use cyclic\nwraparound only when the source declares it;
:Minimize the complete named weighted objective;
:Extract one sequence; independently evaluate\nordered tuples, eligible starts and active overlaps;
:Check feasibility and agreement with solver objective;\nuse exact final-output evaluation for metrics;
stop
""",
"mip-solver-and-solution-audit": r"""
title MIP execution - one solution, one evaluator, truthful certificate
start
:Discover callable installed solvers;\ntry PySCIPOpt before concluding none is available;
:Build intended integer model, hard constraints,\nlinked auxiliary variables and complete objective;
:Set time limit; optimize;\ncapture status, incumbent, bound and gap;
if (Feasible incumbent exists?) then (yes)
  :Extract assignments from the selected incumbent;\nuse model.getSolVal(sol,var), not var.getVal();
else (no)
  :Report no feasible solution;\ndo not invent a certificate or valid schedule;
  stop
endif
:Validate extracted hard rules, counts,\neligibility, finite numbers and no duplicates;
:Use pure input + final-output evaluator;\ncompare its objective to the solver objective;
if (Post-processing changed the solution?) then (yes)
  :Disclose change; recompute all metrics;\ndo not transfer old optimality claims blindly;
endif
:Write one final schedule / assignment;
:RELOAD that exact disk artifact;\nvalidate and recompute metrics before writing metrics file;
:Write formulation and report for that same solution;\ninclude variables, constraints, linearization,\nobjective, method, status, limit, bound and gap;
if (Solver certified optimality?) then (yes)
  :Report the supported optimality claim;
else (time / other limit)
  :Report a feasible incumbent and its known gap;
endif
:Reload outputs again; confirm metric consistency;\nfix extraction / semantics before submission if mismatched;
stop
""",
},
"manufacturing-fjsp-optimization": {
"fjsp-baseline-repair-with-downtime-and-policy": r"""
title Flexible job shop repair - precedence, earliest start and budgets
start
:Load baseline, allowed machine durations,\nsorted downtime and policy budgets;
:Sort repair order by operation index,\nbaseline start, then original baseline list index;
while (More operations in precedence-aware order?) is (yes)
  :anchor = max(baseline start,\nnew end of this job's previous operation);
  if (Baseline machine legal?) then (yes)
    :Try baseline machine first;
  else (no)
    :Choose a legal default;\nminimum duration is a suggested heuristic;
  endif
  :For a candidate machine use THAT machine's duration;\nstart t at integer anchor;
  while (Overlap with machine work or downtime?) is (yes)
    :Increment t by exactly +1;\nnever skip unchecked integer start times;
  endwhile (earliest feasible start)
  if (Shift large and machine-change budget remains?) then (yes)
    :Evaluate legal alternate machines with same scan;\nconsider alternate if it reduces start shift;
  endif
  :Choose candidate with policy-aware priorities:\nmachine changes, L1 shift, start, machine ID;\nrespect remaining budgets;
  :Immediately commit operation to machine timeline;\nupdate job predecessor end, change count and L1 shift;
endwhile (no)
:Validate no earlier-than-baseline starts, precedence,\nlegal machines and durations, no work/downtime overlaps;
:Check MC = count(new machine != ORIGINAL machine);\nShift_L1 = sum(abs(new start - baseline start));\nverify budgets and makespan improvement;
note right
  If start > anchor, start - 1 must be infeasible.
  Half-open overlap: s < b AND a < e.
  Preserve the same repair order when committing intervals.
end note
stop
""",
},
}


if __name__ == "__main__":
    for task, skills in DIAGRAMS.items():
        directory = HERE / "tasks" / task / "diagrams"
        directory.mkdir(parents=True, exist_ok=True)
        for skill, body in skills.items():
            (directory / f"{skill}.puml").write_text(STYLE + body.strip() + "\n@enduml\n")
    print("Wrote 13 skill-derived UML sources")
