# Modelo de Dinámica de Sistemas — Expansión de Generación y Transmisión (Brasil / Chile)

Modelo de simulación en **Vensim** que representa, mes a mes y por zonas, la expansión
de capacidad de generación, la expansión de transmisión e interconexiones, la inversión
en recursos distribuidos (DER), el almacenamiento (BESS), las tecnologías de mejora de
red (GET, *Grid Enhancing Technologies*) y el despacho horario con y sin congestión.

Hay **dos instancias del mismo modelo**, una por país: cambian los datos de entrada,
no las ecuaciones (la sección de ecuaciones de `ModeloBR.mdl` y `ModeloCL.mdl` es
idéntica; solo difieren el diagrama y el archivo de datos asociado).

---

## 1. Contenido del repositorio

```
modelo/
  brasil/
    ModeloBR.mdl      Modelo Vensim (texto, editable)   — 743 KB
    ModeloBR.vpmx     Modelo publicado (empaquetado)    — 41 MB
    BRASIL.xlsx       Libro de datos de entrada         — 7.1 MB
  chile/
    ModeloCL.mdl      Modelo Vensim (texto, editable)
    ModeloCL.vpmx     Modelo publicado (empaquetado)
    CHILE.xlsx        Libro de datos de entrada
results/
  BRASIL.xlsx         Copia congelada del libro de datos de la corrida reportada
  CHILE.xlsx          Copia congelada del libro de datos de la corrida reportada
```

> **Nota sobre `results/`:** hoy contiene una **copia de los libros de datos** con los
> que se produjeron los resultados reportados (mismas hojas y mismos valores que
> `modelo/*/`, salvo redondeo de la última cifra al re-guardar). No contiene todavía los
> archivos de salida de Vensim (`.vdfx`) ni las series exportadas. Sirve como
> referencia de *qué datos* generaron los resultados presentados.

### Ficha rápida del modelo

| Elemento | Valor |
|---|---|
| Horizonte | `INITIAL TIME = 0` a `FINAL TIME = 300` **meses** |
| Eje de fechas | Configurado como `YYYY-MM` a partir de **enero 2025** → 2025-01 a 2050-01 |
| Paso de integración | `TIME STEP = 0.25` mes; `SAVEPER = TIME STEP` (1 201 puntos guardados) |
| Zonas | `Z1`–`Z6` (6 zonas por país) |
| Tecnologías | 14: Biomass, WindOnS, WindOffS, PV, HydroDam, HRoR, Thermo1, Thermo2, Geothermal, PVBESSOp1, PVBESSOp2, Other1-3 |
| Zona × tecnología | `ZTech` = 84 elementos |
| Interconexiones | `Int1`–`Int15` (pares de zonas) |
| Resolución horaria | `Hour` = `H0`–`H23` (día típico) |
| Años de pronóstico | `ForecastYear` = `f0, f1, f3, f5, f7, f9` |
| Llamadas a Excel | 289 (`GET XLS CONSTANTS` / `GET XLS DATA` / `GET XLS SUBSCRIPT`) |
| Vistas del diagrama | Graphs, Parameters, Analysis Variables, Generation Expansion, Transmission Expansion, Availability Need, Dispatch, DER Investment, Hydro, Tariff, BESS |

---

## 2. Requisitos — qué debe tener la instalación de Vensim DSS

El modelo **no corre en Vensim PLE ni PLE Plus**. Requiere **Vensim DSS** (se recomienda
la versión de **64 bits**, Vensim 8 o superior, que es la que produce el formato `.vpmx`).
Estas son las razones concretas, todas verificables abriendo el `.mdl`:

| Requisito | Por qué | Dónde se ve |
|---|---|---|
| **Subíndices / arreglos** | Todo el modelo está dimensionado por zona, tecnología, hora, interconexión y año de pronóstico. PLE no soporta subíndices. | Familias `Zone`, `Tech`, `ZTech`, `Int`, `Hour`, `ForecastYear` |
| **Funciones de lectura de Excel** | 289 llamadas `GET XLS ...`. Vensim lee el `.xlsx` a través de Excel, de modo que **Microsoft Excel debe estar instalado**, en la misma arquitectura que Vensim (64 bits con 64 bits). | `GET XLS CONSTANTS`, `GET XLS DATA` |
| **`GET XLS SUBSCRIPT`** | Los rangos de subíndices (`Z1Tech`…`Z6Tech`, `EnergyUsers`) se **leen desde el libro**. Sin el Excel accesible el modelo **ni siquiera carga**: falla la definición de subíndices, no solo los datos. | Hojas `Base` (C1:P1, Q1:AD1, …) y `Energy Users` |
| **Funciones avanzadas** | `ALLOCATE BY PRIORITY` (21 usos, asignación de despacho y de capacidad), `VECTOR RANK` (8), `DELAY MATERIAL` (19), `ELMCOUNT`, `VMAX` — no disponibles en las ediciones básicas. | Módulos de despacho e inversión |
| **Variables `GAME`** | 4 variables (`Congested Dispatch`, `Congested Dispatch Price`, `Max Interconnection Dispatch`, `Max Interconnection Capacity`) están definidas como `GAME(0)`: se alimentan **desde fuera** durante la corrida. Es el punto de acople con **PyPSA**, y el control externo de Vensim (DLL / scripts de comando) es funcionalidad de **DSS**. | Líneas 8499–8533 de `ModeloBR.mdl` |
| **64 bits y memoria** | Arreglos como `Congested Dispatch[ForecastYear, ZTech, Hour]` = 6 × 84 × 24 valores, guardados en 1 201 pasos. El `.vdfx` resultante pesa cientos de MB. Reserve ≥ 8 GB de RAM libres y espacio en disco. | Sección `.Control` |

**Resumen para el jurado:** Vensim DSS (64 bits) + Microsoft Excel instalado + Windows.
Quien solo quiera *ver* el modelo sin licencia puede usar el **Vensim Model Reader**
(gratuito) con los archivos `.vpmx`: permite abrir y navegar el modelo publicado, pero no
editar ecuaciones. Para reproducir corridas y para el acople con PyPSA se necesita DSS.

---

## 3. Cómo correr el modelo

### 3.1 Preparación (importante)

1. **Descargue el repositorio a una carpeta local del disco.** No lo ejecute desde una
   carpeta sincronizada en la nube con archivos "solo en línea": Vensim necesita el
   `.xlsx` físicamente presente. En OneDrive, marque la carpeta como
   *Conservar siempre en este dispositivo*.
2. **No mueva ni renombre los `.xlsx`.** Cada modelo tiene grabado un alias de archivo:

   | Modelo | Alias | Archivo esperado |
   |---|---|---|
   | `ModeloBR.mdl` | `?Datos` | `BRASIL.xlsx` (misma carpeta) |
   | `ModeloCL.mdl` | `?Datos` | `CHILE.xlsx` (misma carpeta) |

   Todas las ecuaciones referencian `'?Datos'`. Si el nombre o la ubicación cambian,
   Vensim pedirá el archivo al cargar.
3. **Cierre el libro en Excel** antes de simular (o ábralo en solo lectura), para evitar
   bloqueos de archivo.

### 3.2 Corrida estándar (Vensim DSS)

1. Abra **Vensim DSS** → `File > Open Model…` → `modelo/brasil/ModeloBR.mdl`
   (o `modelo/chile/ModeloCL.mdl`).
2. Espere a que termine de leer el Excel: durante la carga se resuelven los subíndices y
   las ~289 constantes y series. Si aparece un cuadro pidiendo un archivo, es el alias
   `?Datos` (ver 3.1, punto 2).
3. Escriba un nombre de corrida en la caja **Run name** de la barra superior
   (por ejemplo `BR_base`), para no sobrescribir corridas previas.
4. Presione **Run**. El modelo simula 300 meses con paso de 0.25 mes.
5. Revise resultados con las vistas y los gráficos predefinidos (sección 5).

> **SyntheSim** (el botón de la varita) permite mover parámetros con deslizadores y ver el
> efecto en tiempo real; es la forma más rápida de explorar sensibilidad sin editar Excel.

### 3.3 Modo publicado (`.vpmx`)

`ModeloBR.vpmx` y `ModeloCL.vpmx` son el modelo **publicado**. Se abren con Vensim DSS o
con el Vensim Model Reader (`File > Open Model`) y sirven para revisar y simular sin tocar
el `.mdl`. Si al abrirlo pidiera el libro de datos, indique la copia de `modelo/<país>/`.

### 3.4 Corrida acoplada con PyPSA (opcional)

El interruptor `Congested Dispatch` (hoja `General Parameters`, celda **B24**) define de
dónde viene el despacho:

| Valor | Significado |
|---|---|
| `0` | Despacho calculado **dentro de Vensim** (formulación nueva) — **es el valor configurado hoy en ambos países** |
| `1` | Despacho **externo, calculado por PyPSA**, entregado a Vensim por las variables `GAME` |
| `-1` | Despacho Vensim, formulación antigua (comparación) |

> ⚠️ **No cambie B24 a `1` en una corrida normal.** Con el valor `1` el modelo espera que
> un proceso externo escriba las variables `GAME` en cada paso; si nadie las alimenta, el
> despacho congestionado queda en cero y los resultados pierden sentido. La corrida
> reproducible para el jurado es con **B24 = 0**.

---

## 4. Escenarios: los interruptores del modelo

Todos viven en la hoja **`General Parameters`** del libro de cada país. Se cambian en
Excel, se guarda el libro y se vuelve a correr el modelo; no hay que editar ecuaciones.

| Celda | Parámetro | Valor actual BR / CL | Significado |
|---|---|---|---|
| `B1` | Zonal Prices? | 1 / 1 | 0 = precio único, 1 = precios zonales |
| `B11` | Desired Availability Margin | 0.35 / 0.70 | Margen de disponibilidad deseado |
| `B12` | Planned Generation Switch | 1 / 1 | 1 = expansión planificada exógena, 0 = endógena |
| `B13` | Endogenous Margin Generation Switch | 0 / 0 | 0 = margen endógeno |
| `B14` | DER Expansion Switch | 1 / 1 | 1 = con DER endógeno |
| `B15` | Planned DER Expansion Switch | 0 / 0 | 1 = DER planificado exógeno |
| `B16` | Only Margin Investments | 0 / 0 | 0 = inversión por rentabilidad, 1 = por margen |
| `B17` | Only RES Investment Margin | 0 / 0 | 1 = margen solo con renovables |
| `B18` | Only RES New Investments | 1 / 1 | 1 = nuevas inversiones solo renovables |
| `B19` | Only Power Allocation | 0 / 0 | 0 = energía y potencia |
| `B20` | MWh → GWh | 1000 / 1000 | Factor de conversión |
| `B21` | Other Generation and Demand | 0 / 0 | Activa tecnologías y demanda "Other" |
| `B22` | GETs | 1 / 1 | 1 = tecnologías de mejora de red activas |
| `B23` | BESS | 1 / 1 | 1 = almacenamiento activo |
| `B24` | Congested Dispatch | 0 / 0 | Ver 3.4 |
| `B27`, `C27` | Curva DER por rentabilidad | 0.01 / 300 (BR); 0.01 / 400 (CL) | Parámetros `c1`, `c2` de la sigmoide |
| `B28`, `C28` | Curva DER por influencia social | −10 / 0.6 | Parámetros `c1`, `c2` |

**Escenario de demanda:** en la hoja `Peak Demand`, la celda **L1** selecciona la
trayectoria: `1` = alta, `0` = media, `-1` = baja. La fórmula de la columna `TOTAL` (G)
elige la columna correspondiente, y esa columna es la que alimenta al modelo.

---

## 5. Cómo revisar el modelo

### 5.1 Recorrido sugerido del diagrama (11 vistas)

| Vista | Qué revisar |
|---|---|
| **Parameters** | Todas las constantes de entrada, con su origen en Excel |
| **Analysis Variables** | Las ~48 variables de salida agregadas: capacidad, despacho, márgenes, tarifa, DER, reservorios |
| **Generation Expansion** | Cadena de inversión: potencial → decisión → licencia → construcción → capacidad operativa |
| **Transmission Expansion** | Necesidad de red por demanda y por generación, km y costo |
| **Availability Need** | Margen de disponibilidad frente al deseado (motor de la inversión por margen) |
| **Dispatch** | Despacho horario, precio zonal, congestión, interconexiones |
| **DER Investment** | Adopción distribuida (curvas de rentabilidad e influencia social) |
| **Hydro** | Reservorios, aportes, precio de oferta hidráulica |
| **Tariff** | Formación de la tarifa al usuario |
| **BESS** | Capacidad y duración del almacenamiento |
| **Graphs** | 23 gráficos predefinidos, listos para leer |

Gráficos ya construidos en el modelo, entre otros: `Generation_Capacity_by_Tech`,
`Generation_Capacity_Availability_&_Residual_Demand`, `Availability_Margin`,
`Transmission_km`, `Reservoir_level`, `DER_Capacity_vs_Generation_&_Tariff`,
`Imbalances_and_Interconnection_Z1`…`Z5`, `Generation_Capacity_Z1`…`Z6`, `Demand_Z1`…`Z6`.

### 5.2 Verificaciones de estructura (dentro de Vensim)

- `Model > Check Model` — consistencia de ecuaciones y subíndices.
- `Model > Units Check` — las variables principales de stock y flujo están documentadas
  (MW, MWh, Months, km, USD); varias auxiliares no tienen unidad declarada.
- Herramientas del panel lateral sobre cualquier variable: **Causes Tree** (de qué
  depende), **Uses Tree** (a qué alimenta), **Document** (ecuación, unidad y comentario) y
  **Causal Tracing** para seguir un comportamiento hasta su origen.
- `Model > Document…` exporta el listado completo de ecuaciones a texto, para revisión
  fuera de Vensim.

### 5.3 Verificaciones de comportamiento sugeridas

1. **Balance oferta–demanda:** `Total Generation Capacity` frente a `National Peak Demand`;
   `Availability Margin` debe oscilar alrededor de `Desired Availability Margin`.
2. **Consistencia de la cadena de inversión:** la capacidad que entra en operación
   corresponde a `Decided Generation Investment by Tech` desplazada por los rezagos.
3. **Rezagos:** `Accumulated Generation Delays` = tiempo de construcción + licencia +
   otros retrasos; verificar el desfase con que aparece la capacidad.
4. **Interconexión:** `Total GET Capacity Used` ≤ `Interconnection Capacity` ×
   `Allowed GET Percentage`.
5. **Sensibilidad rápida:** con SyntheSim mover `Desired Availability Margin` y observar la
   respuesta de la inversión; apagar `GETs` (B22 = 0) o `BESS` (B23 = 0) y comparar corridas.
6. **Comparación de corridas:** cargue dos `.vdfx` en el panel de control de Vensim
   (pestaña de *datasets*) y grafique las series superpuestas.

### 5.4 Trazabilidad de los datos

La primera hoja de cada libro (`Brasil` / `Chile`) es una **tabla de fuentes**: para cada
dato indica la metodología, en qué pestaña del libro se ubica y el enlace público de
origen (ONS y EPE en el caso de Brasil). Es el punto de partida para auditar cualquier
valor de entrada.

Hojas de entrada y su rol principal:

| Hoja | Contenido |
|---|---|
| `General Parameters` | Interruptores de escenario y parámetros globales |
| `Base` | Capacidad inicial por zona y tecnología, precios de oferta, nombres de subíndices |
| `Generation Project Size`, `Potential Expansion`, `Generation Expansion` | Tamaño de proyecto y potencial de expansión |
| `Availability Factor` | Factores de disponibilidad horarios por tecnología |
| `Gen Investment parameters`, `Trans Investment parameters` | Rezagos y costos de inversión |
| `Peak Demand`, `National demand`, `Demand by Zone`, `Demand Curve`, `Alternative demand` | Demanda de potencia y energía, perfil horario y reparto zonal |
| `Interconnections` | Pares de zonas, longitudes y capacidad inicial de interconexión |
| `Hydro` | Aportes, capacidad de reservorio, precios |
| `BESS`, `Zone`, `Energy Users`, `LCOE`, `Planned DER Expansion` | Almacenamiento, DER, tipos de usuario, costos nivelados |
| `Cumulative capacity in 3/5/7/9 years`, `Cumulative trans in 7 years`, `Transmission Expansion` | Planes de expansión anunciados que alimentan `ForecastYear` |

---

## 6. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Vensim pide un archivo al abrir el modelo | El alias `?Datos` no encuentra `BRASIL.xlsx` / `CHILE.xlsx`. Deje el `.xlsx` en la misma carpeta que el `.mdl`, con ese nombre exacto |
| Error de subíndices al cargar | El libro no es legible: archivo "solo en línea", ruta inaccesible o Excel no instalado. Los subíndices se leen con `GET XLS SUBSCRIPT` |
| Constantes en cero o valores extraños | El libro estaba abierto y bloqueado, o se renombró una hoja. Los nombres de hoja deben conservarse exactamente |
| El despacho congestionado sale en cero | `Congested Dispatch` (B24) quedó en `1` sin el acople externo activo. Vuelva a `0` |
| La corrida es lenta o el `.vdfx` es enorme | Es esperable: 1 201 pasos guardados sobre arreglos de hasta 6 × 84 × 24. Use disco local y Vensim de 64 bits |
| Números mal interpretados desde Excel | Configuración regional con coma decimal frente a un libro con punto decimal. Alinee la configuración regional de Windows con el formato del libro |

---

## 7. Reproducir los resultados reportados

1. Use los libros de `modelo/brasil/` y `modelo/chile/` **sin modificar** (la copia de
   `results/` es equivalente: solo difiere en el redondeo de la última cifra al re-guardar).
2. Verifique que `General Parameters!B24 = 0` y que los demás interruptores coinciden con
   la tabla de la sección 4.
3. Corra `ModeloBR.mdl` con nombre de corrida `BR_base` y `ModeloCL.mdl` con `CL_base`.
4. Exporte las series de la vista **Analysis Variables** (`Model > Export Dataset…` a
   `.tab` o `.xlsx`) para comparar y documentar.
