# System Dynamics Model — Generation and Transmission Expansion (Brazil / Chile)

This **Vensim** simulation model represents, month by month and by zone, the expansion of generation capacity, transmission and interconnections, investment in distributed energy resources (DER), battery energy storage systems (BESS), grid-enhancing technologies (GETs), and hourly dispatch with and without congestion.

The repository contains **two instances of the same model**, one for each country. The input data differ, but the equations do not: the equation sections of `ModeloBR.mdl` and `ModeloCL.mdl` are identical; only the diagram and associated data file differ.

---

## 1. Repository contents

```
modelo/
  brasil/
    ModeloBR.mdl      Vensim model (editable text)       — 743 KB
    ModeloBR.vpmx     Published model (packaged)         — 41 MB
    BRASIL.xlsx       Input data workbook                — 7.1 MB
  chile/
    ModeloCL.mdl      Vensim model (editable text)
    ModeloCL.vpmx     Published model (packaged)
    CHILE.xlsx        Input data workbook
results/
  BRASIL.xlsx         Frozen copy of the workbook used for the reported run
  CHILE.xlsx          Frozen copy of the workbook used for the reported run
```

> **Note on `results/`:** this directory currently contains **copies of the data workbooks** used to produce the reported results. They have the same sheets and values as those under `modelo/*/`, except for possible rounding in the last digit after re-saving. It does not yet contain Vensim output files (`.vdfx`) or exported time series. Its purpose is to document *which data* generated the presented results.

### Model at a glance

| Item | Value |
|---|---|
| Time horizon | `INITIAL TIME = 0` to `FINAL TIME = 300` **months** |
| Date axis | Configured as `YYYY-MM`, starting in **January 2025** → 2025-01 to 2050-01 |
| Integration step | `TIME STEP = 0.25` month; `SAVEPER = TIME STEP` (1,201 saved points) |
| Zones | `Z1`–`Z6` (6 zones per country) |
| Technologies | 14: Biomass, WindOnS, WindOffS, PV, HydroDam, HRoR, Thermo1, Thermo2, Geothermal, PVBESSOp1, PVBESSOp2, Other1-3 |
| Zone × technology | `ZTech` = 84 elements |
| Interconnections | `Int1`–`Int15` (zone pairs) |
| Hourly resolution | `Hour` = `H0`–`H23` (representative day) |
| Forecast years | `ForecastYear` = `f0, f1, f3, f5, f7, f9` |
| Excel calls | 289 (`GET XLS CONSTANTS` / `GET XLS DATA` / `GET XLS SUBSCRIPT`) |
| Diagram views | Graphs, Parameters, Analysis Variables, Generation Expansion, Transmission Expansion, Availability Need, Dispatch, DER Investment, Hydro, Tariff, BESS |

---

## 2. Requirements — what the Vensim DSS installation must include

The model **does not run in Vensim PLE or PLE Plus**. It requires **Vensim DSS**. The **64-bit version**, Vensim 8 or later, is recommended and is the version that produces the `.vpmx` format. The specific reasons, all verifiable by opening the `.mdl` file, are listed below.

| Requirement | Why it is needed | Where to find it |
|---|---|---|
| **Subscripts / arrays** | The entire model is dimensioned by zone, technology, hour, interconnection, and forecast year. PLE does not support subscripts. | Families `Zone`, `Tech`, `ZTech`, `Int`, `Hour`, `ForecastYear` |
| **Excel data functions** | There are 289 `GET XLS ...` calls. Vensim reads the `.xlsx` file through Excel, so **Microsoft Excel must be installed** and must use the same architecture as Vensim (64-bit with 64-bit). | `GET XLS CONSTANTS`, `GET XLS DATA` |
| **`GET XLS SUBSCRIPT`** | Subscript ranges (`Z1Tech`…`Z6Tech`, `EnergyUsers`) are **read from the workbook**. If Excel is unavailable, the model **cannot even load**: subscript definitions fail, not just the data import. | `Base` sheet (C1:P1, Q1:AD1, …) and `Energy Users` sheet |
| **Advanced functions** | `ALLOCATE BY PRIORITY` (21 uses, for dispatch and capacity allocation), `VECTOR RANK` (8), `DELAY MATERIAL` (19), `ELMCOUNT`, and `VMAX` are unavailable in the basic editions. | Dispatch and investment modules |
| **`GAME` variables** | Four variables (`Congested Dispatch`, `Congested Dispatch Price`, `Max Interconnection Dispatch`, and `Max Interconnection Capacity`) are defined as `GAME(0)` and receive values **from an external process** during a run. This is the integration point with **PyPSA**; external control through the Vensim DLL or command scripts is a **DSS** feature. | Lines 8499–8533 of `ModeloBR.mdl` |
| **64-bit architecture and memory** | Arrays such as `Congested Dispatch[ForecastYear, ZTech, Hour]` contain 6 × 84 × 24 values, saved over 1,201 time steps. The resulting `.vdfx` file can be hundreds of megabytes. Keep at least 8 GB of RAM available and sufficient disk space. | `.Control` section |

**In summary:** use Vensim DSS (64-bit) with Microsoft Excel installed on Windows. Anyone who only needs to *view* the model without a license can use the free **Vensim Model Reader** with the `.vpmx` files. It can open and navigate the published model but cannot edit equations. Reproducing runs and integrating with PyPSA require DSS.

---

## 3. Running the model

### 3.1 Preparation (important)

1. **Download the repository to a local folder.** Do not run it from a cloud-synced folder containing online-only files: Vensim needs the `.xlsx` file to be physically available. In OneDrive, select *Always keep on this device* for the folder.
2. **Do not move or rename the `.xlsx` files.** Each model stores a file alias:

   | Model | Alias | Expected file |
   |---|---|---|
   | `ModeloBR.mdl` | `?Datos` | `BRASIL.xlsx` (in the same folder) |
   | `ModeloCL.mdl` | `?Datos` | `CHILE.xlsx` (in the same folder) |

   Every relevant equation refers to `'?Datos'`. If the file name or location changes, Vensim will prompt for the file when loading the model.
3. **Close the workbook in Excel** before running the simulation, or open it as read-only, to avoid file-locking issues.

### 3.2 Standard run (Vensim DSS)

1. Open **Vensim DSS** → `File > Open Model…` → `modelo/brasil/ModeloBR.mdl` (or `modelo/chile/ModeloCL.mdl`).
2. Wait for the Excel import to finish. Vensim resolves the subscripts and approximately 289 constants and time series while loading. If a dialog prompts for a file, it refers to the `?Datos` alias (see Section 3.1, step 2).
3. Enter a run name in the **Run name** box on the top toolbar, such as `BR_base`, to avoid overwriting previous runs.
4. Select **Run**. The model simulates 300 months with a 0.25-month time step.
5. Review the results using the predefined views and graphs described in Section 5.

> **SyntheSim** (the magic-wand button) lets you adjust parameters with sliders and see the effect in real time. It is the quickest way to explore sensitivity without editing the Excel workbook.

### 3.3 Published mode (`.vpmx`)

`ModeloBR.vpmx` and `ModeloCL.vpmx` are the **published** versions of the models. Open them with Vensim DSS or Vensim Model Reader (`File > Open Model`) to review and simulate the model without modifying the `.mdl` file. If prompted for the data workbook, select the copy under `modelo/<country>/`.

### 3.4 Coupled run with PyPSA (optional)

The `Congested Dispatch` switch on the `General Parameters` sheet, cell **B24**, defines the source of dispatch values:

| Value | Meaning |
|---|---|
| `0` | Dispatch calculated **within Vensim** using the new formulation — **the current setting for both countries** |
| `1` | **External dispatch calculated by PyPSA** and passed to Vensim through the `GAME` variables |
| `-1` | Dispatch calculated in Vensim using the previous formulation, for comparison |

> ⚠️ **Do not change B24 to `1` for a standard run.** With a value of `1`, the model expects an external process to write the `GAME` variables at every time step. If no process supplies them, congested dispatch remains zero and the results are not meaningful. Use **B24 = 0** for the reproducible baseline run.

---

## 4. Scenarios: model switches

All switches are on the **`General Parameters`** sheet of each country's workbook. Change them in Excel, save the workbook, and run the model again; the equations do not need to be edited.

| Cell | Parameter | Current BR / CL value | Meaning |
|---|---|---|---|
| `B1` | Zonal Prices? | 1 / 1 | 0 = single price; 1 = zonal prices |
| `B11` | Desired Availability Margin | 0.35 / 0.70 | Target availability margin |
| `B12` | Planned Generation Switch | 1 / 1 | 1 = exogenous planned expansion; 0 = endogenous expansion |
| `B13` | Endogenous Margin Generation Switch | 0 / 0 | 0 = endogenous margin |
| `B14` | DER Expansion Switch | 1 / 1 | 1 = endogenous DER enabled |
| `B15` | Planned DER Expansion Switch | 0 / 0 | 1 = exogenous planned DER |
| `B16` | Only Margin Investments | 0 / 0 | 0 = profitability-based investment; 1 = margin-based investment |
| `B17` | Only RES Investment Margin | 0 / 0 | 1 = margin met only with renewable energy sources |
| `B18` | Only RES New Investments | 1 / 1 | 1 = new investment limited to renewable energy sources |
| `B19` | Only Power Allocation | 0 / 0 | 0 = energy and power |
| `B20` | MWh → GWh | 1000 / 1000 | Conversion factor |
| `B21` | Other Generation and Demand | 0 / 0 | Enables `Other` technologies and demand |
| `B22` | GETs | 1 / 1 | 1 = grid-enhancing technologies enabled |
| `B23` | BESS | 1 / 1 | 1 = storage enabled |
| `B24` | Congested Dispatch | 0 / 0 | See Section 3.4 |
| `B27`, `C27` | Profitability-driven DER curve | 0.01 / 300 (BR); 0.01 / 400 (CL) | Sigmoid parameters `c1`, `c2` |
| `B28`, `C28` | Social-influence DER curve | −10 / 0.6 | Parameters `c1`, `c2` |

**Demand scenario:** cell **L1** on the `Peak Demand` sheet selects the trajectory: `1` = high, `0` = medium, and `-1` = low. The formula in the `TOTAL` column (G) selects the corresponding column, which then supplies the model.

---

## 5. Reviewing the model

### 5.1 Suggested tour of the diagram (11 views)

| View | What to review |
|---|---|
| **Parameters** | All input constants and their Excel sources |
| **Analysis Variables** | Approximately 48 aggregated output variables: capacity, dispatch, margins, tariff, DER, and reservoirs |
| **Generation Expansion** | Investment chain: potential → decision → licensing → construction → operating capacity |
| **Transmission Expansion** | Grid requirements driven by demand and generation, including distance and cost |
| **Availability Need** | Availability margin relative to its target, which drives margin-based investment |
| **Dispatch** | Hourly dispatch, zonal prices, congestion, and interconnections |
| **DER Investment** | Distributed adoption through profitability and social-influence curves |
| **Hydro** | Reservoirs, inflows, and hydropower offer price |
| **Tariff** | End-user tariff formation |
| **BESS** | Storage capacity and duration |
| **Graphs** | 23 predefined, ready-to-use graphs |

Predefined graphs include `Generation_Capacity_by_Tech`, `Generation_Capacity_Availability_&_Residual_Demand`, `Availability_Margin`, `Transmission_km`, `Reservoir_level`, `DER_Capacity_vs_Generation_&_Tariff`, `Imbalances_and_Interconnection_Z1`…`Z5`, `Generation_Capacity_Z1`…`Z6`, and `Demand_Z1`…`Z6`.

### 5.2 Structural checks in Vensim

- `Model > Check Model` — checks equation and subscript consistency.
- `Model > Units Check` — the main stock and flow variables document their units (MW, MWh, Months, km, and USD); several auxiliary variables have no declared unit.
- Use the side-panel tools on any variable: **Causes Tree** shows its dependencies, **Uses Tree** shows what it supplies, **Document** displays its equation, unit, and comment, and **Causal Tracing** helps trace behavior back to its origin.
- `Model > Document…` exports the complete equation listing as text for review outside Vensim.

### 5.3 Suggested behavioral checks

1. **Supply-demand balance:** compare `Total Generation Capacity` with `National Peak Demand`; `Availability Margin` should fluctuate around `Desired Availability Margin`.
2. **Investment-chain consistency:** capacity entering operation should correspond to `Decided Generation Investment by Tech`, shifted by the relevant delays.
3. **Delays:** `Accumulated Generation Delays` equals construction time plus licensing and other delays; verify the lag before capacity becomes available.
4. **Interconnections:** `Total GET Capacity Used` ≤ `Interconnection Capacity` × `Allowed GET Percentage`.
5. **Quick sensitivity test:** use SyntheSim to adjust `Desired Availability Margin` and observe the investment response. Disable `GETs` (B22 = 0) or `BESS` (B23 = 0) and compare the runs.
6. **Run comparison:** load two `.vdfx` files in the Vensim control panel under the *datasets* tab and plot the time series together.

### 5.4 Data traceability

The first sheet in each workbook (`Brasil` / `Chile`) is a **source table**. For every input, it identifies the methodology, the workbook sheet where the value is located, and a public source link (including ONS and EPE for Brazil). Use it as the starting point for auditing any input value.

Input sheets and their primary roles:

| Sheet | Contents |
|---|---|
| `General Parameters` | Scenario switches and global parameters |
| `Base` | Initial capacity by zone and technology, offer prices, and subscript names |
| `Generation Project Size`, `Potential Expansion`, `Generation Expansion` | Project sizes and expansion potential |
| `Availability Factor` | Hourly availability factors by technology |
| `Gen Investment parameters`, `Trans Investment parameters` | Investment delays and costs |
| `Peak Demand`, `National demand`, `Demand by Zone`, `Demand Curve`, `Alternative demand` | Peak and energy demand, hourly profiles, and zonal distribution |
| `Interconnections` | Zone pairs, line lengths, and initial interconnection capacity |
| `Hydro` | Inflows, reservoir capacity, and prices |
| `BESS`, `Zone`, `Energy Users`, `LCOE`, `Planned DER Expansion` | Storage, DER, user types, and levelized costs |
| `Cumulative capacity in 3/5/7/9 years`, `Cumulative trans in 7 years`, `Transmission Expansion` | Announced expansion plans that supply `ForecastYear` |

---

## 6. Troubleshooting

| Symptom | Cause and solution |
|---|---|
| Vensim prompts for a file when opening the model | The `?Datos` alias cannot find `BRASIL.xlsx` / `CHILE.xlsx`. Keep the `.xlsx` file in the same folder as its `.mdl` file and preserve the exact file name. |
| Subscript error while loading | The workbook cannot be read because it is online-only, its path is inaccessible, or Excel is not installed. Subscripts are read with `GET XLS SUBSCRIPT`. |
| Constants are zero or values look incorrect | The workbook was open and locked, or a sheet was renamed. Sheet names must be preserved exactly. |
| Congested dispatch is zero | `Congested Dispatch` (B24) is set to `1` without an active external integration. Change it back to `0`. |
| The run is slow or the `.vdfx` file is very large | This is expected: 1,201 time steps are saved for arrays containing up to 6 × 84 × 24 elements. Use local storage and 64-bit Vensim. |
| Excel numbers are interpreted incorrectly | The operating system's regional settings use a decimal comma while the workbook uses a decimal point, or vice versa. Align the Windows regional settings with the workbook's number format. |

---

## 7. Reproducing the reported results

1. Use the workbooks under `modelo/brasil/` and `modelo/chile/` **without modifying them**. The copies under `results/` are equivalent except for possible rounding in the last digit after re-saving.
2. Confirm that `General Parameters!B24 = 0` and that the other switches match the table in Section 4.
3. Run `ModeloBR.mdl` with the run name `BR_base` and `ModeloCL.mdl` with `CL_base`.
4. Export the time series from the **Analysis Variables** view using `Model > Export Dataset…` to `.tab` or `.xlsx` for comparison and documentation.
