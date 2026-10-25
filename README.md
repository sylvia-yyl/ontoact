# OntoAct

**From ontology to reviewed actions.** OntoAct turns operational data into an ontology of business objects, lets you ask questions that are answered by walking that graph, and turns the answer into actions you can simulate, compare, review, apply and undo.

The bundled case is quarterly production planning on real customer demand from the [DataCo Smart Supply Chain](https://doi.org/10.17632/8gx2fvg2k6.5) dataset: five product lines that share materials, suppliers and a flex line, so fixing one line can help or hurt another.

<!-- SCREENSHOT: ontology overview with the coupled graph -->

## What you can do with it

| Question | What OntoAct does |
|---|---|
| "We are short of the quarter's revenue target. Why, and what is the best set of actions?" | Traces late orders to their root-cause parts and suppliers, evaluates combinations of expedites, rework, line moves and policy changes, and shows the cost / revenue / harmed-orders trade-off |
| "A supplier is down for three weeks. Which lines, orders and customers are hit, and what do we do?" | Follows the outage through purchase orders, shared parts and bills of materials to every affected order, then proposes recovery plans |
| "A corporate customer wants 30% more bikes. Do we accept, and who gets squeezed?" | Re-plans with the extra demand and lists the orders on other lines that lose material or capacity |

Every number on screen comes from a deterministic simulation. An explanation written by an LLM is checked against those numbers before it is shown as verified.

## How it works

```
DataCo CSV
  -> import and map to a knowledge graph
  -> Ontology objects: orders, product lines, items, BOM lines, stock, purchase orders, suppliers
  -> question answering over the graph, citing the objects it used
  -> candidate actions, each evaluated by re-running the same simulation
  -> explanation, with every number checked against the simulation
  -> Decision Package: submit -> review -> apply as Ontology edits -> revert
```

| Step | Status |
|---|---|
| Pack generator: real demand, rule-derived supply with shared materials and a flex line | Built |
| Supplier capacity, plant transfers, customer segments and late penalties | In progress |
| Import and graph mapping with [Semantica](https://github.com/Hawksight-AI/semantica) | Planned |
| Graph question answering | Planned |
| Ontology query core, versioned queries, MCP endpoint | Built |
| Scenario studies, candidate evaluation, explanation check | Built |
| Decision Packages: review, apply, revert, audit trail | Built |
| Workshop apps: configurable pages bound to Ontology data | Built |

<!-- Update this table as steps land; remove it once every step is built. -->

## Quick start

Requirements: Docker with Compose, and a POSIX shell for the bootstrap script.

```sh
sh scripts/bootstrap.sh                 # writes .env with fresh local secrets
docker compose up -d --build
docker compose exec backend python scripts/seed_case.py dataco_mrp
```

Open http://localhost:5173. The API is at http://localhost:8000.

Explanations need an OpenAI-compatible key: set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`) in `.env`, then `docker compose up -d backend`. Everything else works without it.

A second case, container pickup scheduling, shows the same workbench on a different domain:

```sh
docker compose exec backend python scripts/seed_case.py container_scheduling
```

## Walkthroughs

### 1. Close the quarter's revenue gap

<!-- STEPS + SCREENSHOTS: Planning Cockpit -> Demand Explorer -> Material Coverage -> Suggested Actions -> explanation -> Decision Package -->

### 2. Respond to a supplier outage

<!-- STEPS + SCREENSHOTS: outage scenario -> affected subgraph -> recovery candidates -> apply -> revert -->

### 3. Decide on a large extra order

<!-- STEPS + SCREENSHOTS: added demand -> squeezed orders on other lines -> accept / partial / defer candidates -->

## Using the Ontology from an agent

The API serves Ontology queries as tools over the Model Context Protocol (streamable HTTP) at `http://localhost:8000/api/v2/mcp/`. Nothing is open by default: a client sends the bearer token of one MCP scope, sees only the queries that scope lists, and every call runs as the scope's owner, so results are limited to what both the scope and that user allow.

<!-- EXAMPLE: client config and one tool call -->

## Data

| Part | Source |
|---|---|
| Demand: products, prices, order dates, quantities, markets, customer segments, scheduled shipping days | Real. DataCo Smart Supply Chain, Mendeley Data, doi:10.17632/8gx2fvg2k6.5, CC BY 4.0. Cancelled and suspected-fraud orders are dropped; customer identity columns are never read |
| Supply: bills of materials, stock, purchase orders, line capacity, supplier disruptions, quality hold | Rule-derived from the real demand with a fixed seed (no public source exists) |

The pack in `demo_cases/dataco_mrp/` is generated, not hand-edited. To rebuild it, download `DataCoSupplyChainDataset.csv` from the link above and run, with Python 3.12, pandas and `backend/requirements.txt` installed:

```sh
python backend/scripts/build_dataco_pack.py path/to/DataCoSupplyChainDataset.csv
```

The script checks the file's SHA-256 before it reads it. `--variant independent` builds the earlier pack in which every line owns its parts.

## Architecture

| Concern | Implementation |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, react-query, Cytoscape.js, ECharts |
| API | FastAPI, Pydantic, SQLAlchemy |
| Records, runs, packages, audit | PostgreSQL |
| Graph projection for traversal | FalkorDB |
| User Functions | Separate `function-runner` container on an internal network |
| Agent access | MCP Python SDK, streamable HTTP |

<!-- DIAGRAM: services and data flow -->

## Testing

<!-- Unit, known-answer, invariant, end-to-end suites and how to run them -->

## Limitations

- Study runs execute on an in-process thread pool. A run interrupted by a restart is marked failed and can be retried; for production, swap in a task queue.
- The app runs as a single workspace user with no sign-in.
- Supply-side data is rule-derived; only demand is real.

## License

<!-- TBD -->
