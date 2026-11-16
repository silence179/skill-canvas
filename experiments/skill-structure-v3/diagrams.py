"""Skill-derived diagrams only. No task inputs, outcomes or graders are read.

Source labels S1/S2 resolve through the frozen full-local-resource source map.
Numbers in diagrams come only from skill definitions, never benchmark instances.
"""
STYLE = '''digraph skill {
graph [bgcolor="white", pad="0.28", nodesep="0.38", ranksep="0.5", fontname="DejaVu Sans", fontsize=22, labelloc=t, labeljust=l];
node [shape=box, style="rounded,filled", fillcolor="#eef5ff", color="#365a82", fontcolor="#152b44", fontname="DejaVu Sans", fontsize=17, margin="0.16,0.12", penwidth=1.3];
edge [color="#46566f", fontname="DejaVu Sans", fontsize=14, arrowsize=.8];
'''

DECISIONS = {
 "prefix-cache-replay": ("redraw", "state_machine", "驻留状态与带 guard 的 S/M/G 迁移，比单一路径更核心。"),
 "cache-policy-comparison": ("no_new_diagram", "existing_text_table", "原文已是完整的策略比较表；继续保留全文，不另画一张表的截图。"),
 "power-flow-data": ("no_new_diagram", "existing_schema_tables", "主体是字段、索引和单位的查阅契约，原文表格与代码比额外图更直接。"),
 "dc-power-flow": ("redraw", "typed_dataflow", "源与脚本定义数据、矩阵、角度和潮流之间的依赖及函数返回契约。"),
 "economic-dispatch": ("redraw", "variable_constraint_graph", "主体是变量、目标和多组同时成立的约束，不是逐步动作。"),
 "locational-marginal-prices": ("redraw", "paired_dependency_graph", "对偶量依赖约束与单位；base/反事实是共享结构的两支及比较关系。"),
 "state-space-linearization": ("no_new_diagram", "equations_and_code", "很短的公式／离散化查阅卡，保留原文即可；不为流程改流程。"),
 "finite-horizon-lqr": ("redraw", "indexed_recurrence", "核心是 P[k+1] 到 K[k]/P[k] 的索引依赖和逆序递推。"),
 "mpc-horizon-tuning": ("no_new_diagram", "existing_tradeoff_tables", "主体是参数指南与权衡表，无需另造流程，也不加入源未给出的验收标准。"),
 "integral-action-design": ("redraw", "feedback_block", "误差、dt、泄漏、限幅与输出相加，是反馈信号连接。"),
 "ordered-window-sequencing-mip": ("redraw", "aligned_windows_and_constraints", "顺序、共享前后缀和 active-pattern overlap 适合空间对齐。"),
 "mip-solver-and-solution-audit": ("keep_activity", "existing_activity", "原文明确是求解、提取、落盘、复读和审计的操作顺序，现有活动图适配。"),
 "fjsp-baseline-repair-with-downtime-and-policy": ("redraw", "resource_timeline", "主体是前序与机台／停机区间的同时约束，以及逐整数最早可行边界。"),
}

BODIES = {
"prefix-cache-replay": r'''
label="prefix-cache-replay | residency states and event order";
rankdir=LR;
subgraph cluster_states {
 label="Per-block states [S1] | solid edges are state transitions"; color="#ccd8e6";
 absent [label="Absent\nno resident entry"];
 small [label="S: small FIFO\nRESIDENT\nfreq in [0,max_freq]"];
 main [label="M: main FIFO\nRESIDENT\nfreq in [0,max_freq]"];
 ghost [label="G: ghost FIFO\nNOT resident\nhashes only",fillcolor="#fff3d6"];
 absent -> small [label="new access / drain S if full;\nappend (h,0) to S tail"];
 ghost -> main [label="ghost access / remove G;\nadmit_M(h,0)"];
 small -> small [label="resident access / saturate freq;\nFIFO position unchanged"];
 small -> main [label="S-head drained, freq>=1 /\nadmit_M(v,freq); PRESERVE freq"];
 small -> ghost [label="S-head drained, freq=0 / insert_G"];
 main -> main [label="access / saturate freq; no reorder\nM full + head.freq>=1 / pop head;\nfreq--; append TAIL; continue drain"];
 main -> ghost [label="M full: head freq=0 /\npop; insert_G; STOP one real eviction"];
 ghost -> ghost [label="insert_G existing / remove then append"];
 ghost -> absent [label="insert_G new while full / discard oldest"];
}
subgraph cluster_order {
 label="Per-request accounting [S1] | sequence, before state mutation"; color="#ccd8e6";
 before [label="At request arrival:\nresident = S union M\nscan from hash_ids[0], stop at FIRST miss\nhit_tokens = min(k*block_size, input_length)"];
 access [label="Then access EVERY hash in order\napply declared eviction policy\nDo not re-tokenize or re-hash hash_ids"];
 before -> access [label="observe BEFORE mutate"];
}
caps [shape=note,fillcolor="#fff8de",label="S_cap = round(capacity*small_ratio)\nM_cap = capacity-S_cap; G_cap = M_cap\nNew S / ghost->M admissions start freq=0\nDrain before admission; cascades allowed\nfinal_blocks=|S|+|M|; exclude G\nSum per-request prompt/hit; rate=total_hit/total_prompt [S1]\nOther policy? use companion specification [S2]"];
access -> small [style=dashed,label="events affect state",constraint=false];
''',
"dc-power-flow": r'''
label="dc-power-flow | typed data dependencies and script contracts";
rankdir=TB;
input [label="buses + branches + baseMVA [S1,S2]\nmap ORIGINAL bus IDs -> array indices; never ID-1\nDC: lossless, flat voltage, small angles [S1]"];
builder [label="build_susceptance_matrix(branches,buses) [S2]\nx=branch[3]; b=1/x if x!=0 else 0\nB_ff+=b; B_tt+=b; B_ft-=b; B_tf-=b"];
input -> builder [label="arrays"];
matrix [label="B [n_bus x n_bus]"];
sus [label="branch_susceptances\none saved b per branch"];
mapping [label="bus_num_to_idx\noriginal ID -> position"];
builder -> matrix [label="return 1"];
builder -> sus [label="return 2"];
builder -> mapping [label="return 3"];
balance [label="nodal equation [S1]\nPg_pu - Pd_pu = B[i,:] @ theta\nreference bus type=3: theta[slack]=0"];
matrix -> balance [label="model coefficient"];
theta [label="theta [radians]\nfrom the specified model/solve"];
balance -> theta [label="defines constraint",style=dashed];
flows [label="calculate_line_flows(...) [S2]\nflow_MW = saved_b*(theta[f]-theta[t])*baseMVA\nkeep ORIGINAL IDs in returned records\nlimit=branch[5]; loading=abs(flow)/limit*100\nif limit<=0, helper reports loading=0"];
sus -> flows; mapping -> flows; theta -> flows; input -> flows [label="branch data / baseMVA"];
output [label="list of from/to/flow_MW/limit_MW/loading_pct [S2]\nFor OPF: -rate <= flow_MW <= rate [S1]"];
flows -> output;
cli [shape=note,fillcolor="#fff8de",label="CLI prints B size/nonzeros/symmetry only [S2].\nIt does not return a solved OPF or dispatch.\nUse stored susceptances for the flow helper;\nsource inline example and zero-X guard differ."];
builder -> cli [style=dotted,arrowhead=none];
''',
"economic-dispatch": r'''
label="economic-dispatch | variables, objective and simultaneous constraints";
rankdir=TB;
pg [label="Pg[i] [per-unit]\nPg_MW[i]=Pg[i]*baseMVA [S1]"];
rg [label="Rg[i] [MW]\nreserve capacity r_bar[i] [MW] [S1]"];
objective [label="MINIMIZE sum_i C_i(Pg_MW[i]) [S1,S2]\nMODEL=2: highest-order-first coefficients\nNCOST=3: c2*P^2+c1*P+c0; NCOST=2: c1*P+c0\nNCOST=1: constant; NCOST<1: zero (source example)"];
pg -> objective [label="cost argument"];
bounds [label="generator bounds [S1]\ngen[9]/baseMVA <= Pg[i] <= gen[8]/baseMVA"];
reserve [label="reserve bounds + requirement [S1]\n0 <= Rg[i] <= r_bar[i]\nsum_i Rg[i] >= reserve_requirement"];
coupling [label="capacity coupling [S1]\nPg[i]*baseMVA + Rg[i] <= gen[i,8]"];
balance [label="balance alternatives [S1]\naggregate dispatch: sum(Pg)=sum(Pd_MW)/baseMVA\nnetwork DC-OPF: use NODAL balance instead\nmap original generator bus IDs to indices"];
pg -> bounds [label="constrained by",arrowhead=none]; pg -> coupling [arrowhead=none]; rg -> coupling [arrowhead=none]; rg -> reserve [arrowhead=none]; pg -> balance [arrowhead=none];
problem [label="Problem(Minimize(cost), constraints) [S1]\nsource recommends CLARABEL for quadratic network/reserves\nsource notes OSQP may fail on ill-conditioned problems"];
objective -> problem; bounds -> problem; reserve -> problem; coupling -> problem; balance -> problem;
result [label="solved values [S1]\noutput/reserve MW per generator with original bus ID\ntotals: cost $/hr, load/generation/reserve MW\nmargin=sum(Pmax_MW - Pg_MW - Rg_MW)"];
problem -> result;
costnote [shape=note,fillcolor="#fff8de",label="S2: MODEL=1 uses (P,C) breakpoints;\nsource does not provide its optimization implementation.\nS2: marginal cost of quadratic = 2*c2*P+c1.\nGeneral polynomial format vs S1 NCOST>=3 quadratic\nexample is an unresolved source scope difference."];
costnote -> objective [style=dotted,arrowhead=none];
''',
"locational-marginal-prices": r'''
label="locational-marginal-prices | dual dependencies and paired cases";
rankdir=TB;
model [label="balance_constraints[i] references [S1]\ngeneration - load == B[i,:] @ theta\nreserve_con = sum(Rg) >= reserve_requirement"];
base [label="Solve BASE case\ncost / duals / line flows [S1]"];
cf [label="Solve COUNTERFACTUAL\nmodify specified thermal limit; same other inputs [S1]\nsource example factor 1.20; match either endpoint direction"];
model -> base; model -> cf;
dualbase [label="BASE pricing + congestion [S1]\nretain original bus IDs\nLMP source example: dual*baseMVA\nreserve MCP: reserve_con.dual\nNone -> 0 is source fallback, not observed price"];
dualcf [label="COUNTERFACTUAL pricing + congestion [S1]\nsame units / equality direction / ID mapping\nloading=abs(flow_MW)/rating*100\nbinding when loading>=99% (source convention)"];
base -> dualbase; cf -> dualcf;
compare [label="compare cases [S1]\ncost_reduction=base_cost-cf_cost (>=0 for relaxation)\ndelta_LMP[bus]=cf_LMP-base_LMP\nrelieved = binding_before AND NOT binding_after"];
dualbase -> compare [label="base records"]; dualcf -> compare [label="cf records"];
note [shape=note,fillcolor="#fff8de",label="Source convention caveat retained from v2:\nverify normalization/sign against actual equation.\nNo alternative price formula is supplied by this diagram.\nPositive/negative marginal price follows cost response;\nnegative prices are not automatically invalid. [S1]\nFor binding-line calculation source guards x!=0, rate>0."];
model -> note [style=dotted,arrowhead=none];
''',
"finite-horizon-lqr": r'''
label="finite-horizon-lqr | indexed dynamic-programming dependencies";
rankdir=LR;
terminal [label="P[N] = Q\n(or LQR terminal solution) [S1]"];
next [label="P[k+1]\nknown next-stage matrix"];
gain [label="K[k] = solve(\nR + B' P[k+1] B,\nB' P[k+1] A) [S1]"];
current [label="P[k] = Q + A' P[k+1]\n(A - B K[k]) [S1]"];
terminal -> next [label="first: k=N-1"];
next -> gain [label="use P-next"];
next -> current [label="same P-next",constraint=false];
gain -> current [label="K[k]"];
current -> next [label="k <- k-1; continue to 0",constraint=false,color="#b06b30"];
gain -> stored [label="store at index k"];
stored [label="K[:,:,k], all horizon stages\nshape (n_u,n_x,N) [S1]"];
action [label="At each real control timestep [S1]\nmeasure x; recompute horizon solution\napply ONLY u[0] = -K[0] x\nnext real timestep: repeat"];
stored -> action [label="K[0] only"];
sim [shape=note,fillcolor="#fff8de",label="Horizon prediction [S1]:\nu[k]=-K[k] x[k]\nx[k+1]=A x[k]+B u[k]\nJ=sum(x'Qx+u'Ru)+x[N]'P[N]x[N]\nPrediction indices and real time are distinct."];
stored -> sim [style=dotted,arrowhead=none];
''',
"integral-action-design": r'''
label="integral-action-design | per-section feedback signal connections";
rankdir=LR;
ref [label="T_ref[i]"];
meas [label="T[i]"];
err [label="e[i] = T[i] - T_ref[i] [S1]"];
ref -> err [label="minus"]; meas -> err [label="plus"];
scale [label="- c_I * dt [S1]"];
err -> scale;
memory [label="previous u_I[i]\n(one state per section)"];
leak [label="gamma * u_I[i] [S1]"];
memory -> leak;
sum [label="u_I_new[i] = gamma*u_I[i]\n- c_I*dt*(T[i]-T_ref[i]) [S1]"];
scale -> sum; leak -> sum;
clip [label="clip to [-max_integral,+max_integral]\nanti-windup limit [S1]"];
sum -> clip;
clip -> memory [label="store for next timestep",constraint=false,color="#b06b30"];
mpc [label="u_mpc[i]"];
total [label="u_total[i] = u_mpc[i] + u_I[i] [S1]"];
mpc -> total [label="+"];clip -> total [label="+"];
note [shape=note,fillcolor="#fff8de",label="Source tuning guidance, not automatic online adaptation:\nc_I too small: slow correction; too large: oscillation\nsource ranges 0.1-0.5; suggested start 0.1-0.3\ngamma=1 pure integral; gamma<1 leaky\ntypical gamma=0.9-0.99 [S1]\nThis diagram adds no performance thresholds."];
note -> scale [style=dotted,arrowhead=none];
''',
"ordered-window-sequencing-mip": r'''
label="ordered-window-sequencing-mip | aligned ordered windows + constraints";
rankdir=TB;
positions [shape=plain,label=<
<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="12">
<TR><TD BGCOLOR="#dae7f8">position</TD><TD>t</TD><TD>next(t)</TD><TD>next(next(t))</TD><TD>next^3(t)</TD></TR>
<TR><TD BGCOLOR="#dae7f8">item</TD><TD>a</TD><TD>b</TD><TD>c</TD><TD>d</TD></TR>
<TR><TD BGCOLOR="#dae7f8">window A</TD><TD BGCOLOR="#dceee4">a</TD><TD BGCOLOR="#dceee4">b</TD><TD BGCOLOR="#dceee4">c</TD><TD></TD></TR>
<TR><TD BGCOLOR="#dae7f8">window B</TD><TD></TD><TD BGCOLOR="#fff0cd">b</TD><TD BGCOLOR="#fff0cd">c</TD><TD BGCOLOR="#fff0cd">d</TD></TR>
<TR><TD COLSPAN="5">SCHEMATIC adjacency only [S1]: shared suffix/prefix (b,c); labels need not be integers.</TD></TR>
</TABLE>>];
continuity [label="Direct W model: shared ordered prefix/suffix [S1]\nsum_a0 W[t,a0,q1,...,q(r-1)]\n= sum_ar W[next(t),q1,...,q(r-1),ar]\none window per eligible start; required item-role counts\nno repeated items when sequence is a permutation"];
positions -> continuity [label="adjacent windows must agree"];
assignment [label="Alternative: assignment-linked length-r windows [S1]\nz <= each matching assign variable\nz >= sum(matching assign variables) - (r-1)\neach item / required position appears as required"];
positions -> assignment [label="alternative representation"];
active [label="ACTIVE PATTERN contract [S1]\nprimitive offsets + eligible starts + successor map\nbuild active ordered tuples from the global sequence\nfor each candidate extended tuple:\nleft IN active AND right IN active"];
overlap [label="binary overlap O = A AND B [S1]\nO<=A; O<=B; O>=A+B-1\nattach only the defined ordered overlap cost\nkeep it INSIDE the minimized objective"];
active -> overlap [label="membership, not all subsets"];
continuity -> active; assignment -> active;
objective [label="sum named weighted components [S1]\neach uses its own eligible-start mask / tuple offsets\ninclude pairs, triples and required high-order terms\nextract ONE global sequence; independent evaluate(sequence,data)"];
overlap -> objective;
note [shape=note,fillcolor="#fff8de",label="Never sort tuple keys / add reverse pairs without a rule.\nThe drawing above does NOT define every overlap as adjacency:\nactual overlap uses the specified active-pattern membership.\nMissing tuples: follow supplied data contract.\nCyclic continuity ONLY when explicitly defined;\nreporting masks may still exclude boundary starts. [S1]"];
positions -> note [style=dotted,arrowhead=none];
''',
"fjsp-baseline-repair-with-downtime-and-policy": r'''
label="fjsp-baseline-repair-with-downtime-and-policy | symbolic resource timeline";
rankdir=TB;
timeline [shape=plain,label=<
<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="12">
<TR><TD BGCOLOR="#dae7f8">resource</TD><TD>anchor</TD><TD>candidate integers</TD><TD>first feasible t*</TD><TD>end=t*+dur_m</TD></TR>
<TR><TD>job predecessor</TD><TD COLSPAN="2" BGCOLOR="#dceee4">anchor=max(baseline_start, predecessor_new_end)</TD><TD></TD><TD></TD></TR>
<TR><TD>machine m</TD><TD BGCOLOR="#d9dee6">committed work</TD><TD BGCOLOR="#ffe0d8">downtime / conflict</TD><TD COLSPAN="2" BGCOLOR="#dceee4">candidate interval [t*,t*+dur_m)</TD></TR>
<TR><TD COLSPAN="5">SCHEMATIC ONLY [S1,S2]: symbolic intervals, no instance values; rows illustrate constraints, not a schedule.</TD></TR>
</TABLE>>];
order [label="Commit in precedence-aware order [S1]\nsort by (operation index, baseline start, original list index)\nretain ORIGINAL baseline machine/start for budget accounting"];
scan [label="For EACH considered legal machine [S1]\nuse its own processing duration; start at anchor\nwhile conflict with committed work OR downtime: t += 1\nfirst feasible INTEGER t is the candidate\nhalf-open overlap(s,e,a,b): s<b AND a<e"];
order -> scan;timeline -> scan [label="resource/precedence constraints"];
choose [label="Machine choice + budgets [S1]\ntry legal baseline machine first; if illegal choose legal default\nsource: min-duration default / machine-change-first score\nalso source: consider earlier alternate for large shifts\nstate a consistent priority; these heuristics may conflict"];
scan -> choose [label="one earliest feasible candidate per machine"];
commit [label="commit immediately in SAME order [S1]\nupdate machine intervals + job predecessor end\nMC=sum[m_new != m_original]\nL1=sum(abs(start_new-start_original))\nrespect MC/L1 limits; never start before baseline"];
choose -> commit;
commit -> scan [label="next operation; updated state",constraint=false,color="#b06b30"];
check [label="Local timing invariant [S1]\nif start>anchor, start-1 must be infeasible\ncheck legal machine/duration, precedence, overlaps, downtime\npolicy budgets and makespan improvement"];
commit -> check;
note [shape=note,fillcolor="#fff8de",label="S2: repair preserves baseline production commitments.\nS1 safety-bound return alone does not prove feasibility.\nShared reference supplies provenance/difficulty/bibliography,\nnot a new algorithm or instance-specific solution."];
note -> check [style=dotted,arrowhead=none];
''',
}

def dot_source(skill):
    return STYLE + BODIES[skill].strip() + "\n}\n"
