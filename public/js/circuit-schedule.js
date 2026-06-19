// Automatic sequencing for the circuit traveling-pulse animation: turn a set of
// projection arrows into a per-arrow firing order, with no hand-authored path.
//
// This is the "find a reasonable way to start and loop" core, kept apart from the
// rendering (js/circuit-anim.js) so it has *no* three.js dependency and can be
// reasoned about / tested on its own (the data-vs-rendering split this project
// leans on). It reads only structure id + group off each arrow's endpoint meshes.
//
// Model: node = structure, directed edge = arrow (from -> to). Activation spreads
// outward from a seed by breadth-first search; each arrow's slot is the BFS depth
// of its tail, so stepping a clock through the depths (and looping) sweeps a pulse
// around the loop. Robust on any arrow set:
//   - bilateral duplication (every circuit is mirrored, so the arrows form two
//     disjoint L/R loops) -> each weakly-connected component is seeded on its own,
//     so the hemispheres pulse in sync;
//   - a feeder branch off the main cycle (e.g. the nigrostriatal dopamine input
//     into the direct pathway) -> it fires when activation reaches its tail, or at
//     the top of the cycle if the seed never reaches it, instead of breaking a
//     single authored path.

/** Structure id of a region mesh (set in js/main.js buildStructureMesh). */
const nodeId = (mesh) => mesh.userData.structure.id;
/** Region group ("lobe", "basal_ganglia", ...), used by the seed heuristic. */
const nodeGroup = (mesh) => mesh.userData.structure.group;

/**
 * Assign each arrow a firing slot (its tail's BFS depth from a per-component
 * seed) and report how many slots the loop spans.
 * @param {import("./arrows.js").ProjectionArrow[]} circuitArrows
 * @returns {{phased: {arrow: object, phase: number}[], numSteps: number}}
 */
export function scheduleCircuit(circuitArrows) {
  const nodes = new Set();
  const nodeMesh = new Map(); // id -> mesh (for the seed group heuristic)
  const outEdges = new Map(); // id -> arrows leaving it (directed)
  const neighbours = new Map(); // id -> set of ids (undirected, for components)
  const link = (a, b) => {
    if (!neighbours.has(a)) neighbours.set(a, new Set());
    neighbours.get(a).add(b);
  };
  for (const arrow of circuitArrows) {
    const f = nodeId(arrow.fromMesh);
    const t = nodeId(arrow.toMesh);
    nodes.add(f);
    nodes.add(t);
    nodeMesh.set(f, arrow.fromMesh);
    nodeMesh.set(t, arrow.toMesh);
    if (!outEdges.has(f)) outEdges.set(f, []);
    outEdges.get(f).push(arrow);
    link(f, t);
    link(t, f);
  }

  // Weakly-connected components (so the L and R copies are seeded separately).
  const componentOf = new Map();
  let components = 0;
  for (const start of nodes) {
    if (componentOf.has(start)) continue;
    const stack = [start];
    componentOf.set(start, components);
    while (stack.length) {
      const x = stack.pop();
      for (const y of neighbours.get(x) || []) {
        if (!componentOf.has(y)) {
          componentOf.set(y, components);
          stack.push(y);
        }
      }
    }
    components++;
  }
  const componentNodes = Array.from({ length: components }, () => []);
  for (const n of nodes) componentNodes[componentOf.get(n)].push(n);

  // Directed BFS depth per component from a seed: prefer a cortical (lobe) node
  // (these loops are conventionally drawn starting from cortex), else the node
  // that emits the most arrows, else any node.
  const depth = new Map();
  for (const group of componentNodes) {
    let seed = group.find((n) => nodeGroup(nodeMesh.get(n)) === "lobe");
    if (!seed) {
      seed = group.reduce(
        (best, n) =>
          (outEdges.get(n)?.length || 0) > (outEdges.get(best)?.length || 0) ? n : best,
        group[0],
      );
    }
    depth.set(seed, 0);
    const queue = [seed];
    while (queue.length) {
      const x = queue.shift();
      const d = depth.get(x);
      for (const arrow of outEdges.get(x) || []) {
        const y = nodeId(arrow.toMesh);
        if (!depth.has(y)) {
          depth.set(y, d + 1);
          queue.push(y);
        }
      }
    }
    // A pure feeder never reached along directed edges (its tail has no inbound
    // path from the seed) fires at the top of the cycle, injecting its input.
    for (const n of group) if (!depth.has(n)) depth.set(n, 0);
  }

  let maxDepth = 0;
  const phased = circuitArrows.map((arrow) => {
    const phase = depth.get(nodeId(arrow.fromMesh)) ?? 0;
    if (phase > maxDepth) maxDepth = phase;
    return { arrow, phase };
  });
  return { phased, numSteps: maxDepth + 1 };
}
