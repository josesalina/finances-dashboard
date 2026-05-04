# Clustering de Correlaciones del Portfolio

## Qué problema resuelve

Markowitz optimiza pesos asumiendo que conocés la estructura de correlaciones entre activos, pero no la visualiza. En la práctica, un portfolio puede tener 10 tickers que *parecen* diversificados por sector pero se mueven casi juntos (alta correlación). Este análisis agrupa los activos por similitud de comportamiento de retornos para revelar la **diversificación real vs la percibida**.

---

## Concepto central

### Matriz de correlación

Para N activos con retornos diarios `r_i(t)`, la correlación de Pearson entre el activo i y j es:

```
ρ_ij = Cov(r_i, r_j) / (σ_i × σ_j)
```

Los valores van de -1 (movimiento opuesto perfecto) a +1 (movimiento idéntico). La diagonal es siempre 1.

### ¿Por qué clustering?

Con una matriz de correlación N×N es difícil ver la estructura a simple vista. El clustering convierte esa matriz en grupos de activos que se comportan de forma similar, facilitando:

- Detectar concentración de riesgo oculta (todos los "tech" se mueven igual)
- Identificar los activos verdaderamente descorrelacionados (valor para diversificación)
- Guiar rebalanceos: si dos activos están en el mismo cluster, uno puede ser redundante

---

## Dos enfoques

### 1. K-Means sobre la matriz de correlación

**Cómo funciona:**

1. Transformar correlaciones en distancias: `d_ij = sqrt(2 × (1 - ρ_ij))`
   - ρ = 1 (perfectamente correlados) → d = 0
   - ρ = 0 (sin correlación) → d = √2
   - ρ = -1 (anticorrelados) → d = 2
2. Aplicar K-Means sobre las distancias para agrupar activos en K clusters
3. Elegir K óptimo con el método del codo (elbow) o silhouette score

**Ventaja:** rápido, simple, fácil de interpretar  
**Desventaja:** hay que elegir K a priori; K-Means asume clusters esféricos

```python
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import numpy as np

def cluster_kmeans(log_returns, k=3):
    corr = log_returns.corr()
    dist = np.sqrt(2 * (1 - corr))           # distancia de correlación
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(dist)
    return {sym: int(lbl) for sym, lbl in zip(corr.columns, labels)}
```

### 2. Clustering Jerárquico (Hierarchical / Agglomerative)

**Cómo funciona:**

1. Empezar con N clusters (uno por activo)
2. En cada paso, unir los dos clusters más cercanos según un criterio de enlace (`ward`, `complete`, `average`)
3. Resultado: un **dendrograma** que muestra toda la jerarquía de fusiones
4. Cortar el dendrograma a una altura → K clusters

**Ventaja:** no requiere definir K de antemano; el dendrograma es muy informativo visualmente  
**Desventaja:** computacionalmente más costoso para muchos activos (no relevante con N < 100)

```python
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
from scipy.spatial.distance import squareform

def cluster_hierarchical(log_returns, n_clusters=3):
    corr = log_returns.corr()
    dist = np.sqrt(2 * (1 - corr))
    condensed = squareform(dist.values)       # formato requerido por scipy
    Z = linkage(condensed, method="ward")     # matriz de enlace
    labels = fcluster(Z, t=n_clusters, criterion="maxclust")
    return {sym: int(lbl) for sym, lbl in zip(corr.columns, labels)}, Z
```

**Recomendación:** usar jerárquico con `method="ward"` — minimiza la varianza intra-cluster y produce grupos compactos y bien separados.

---

## Integración en el proyecto

### Script sugerido: `backend/scripts/analisis_correlaciones.py`

```python
import yfinance as yf
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

def run_clustering(symbols: list, n_clusters: int = None, period: str = "2y") -> dict:
    """
    Descarga precios históricos y agrupa los activos por correlación de retornos.
    Si n_clusters es None, se elige automáticamente por el método del codo.
    
    Returns dict con:
      - correlation_matrix: matriz ρ_ij
      - distance_matrix: sqrt(2*(1-ρ_ij))
      - clusters: {symbol: cluster_id}
      - cluster_summary: {cluster_id: [symbols, avg_intra_correlation]}
      - linkage_matrix: para renderizar dendrograma en el frontend
    """
    yf_symbols = [s.replace(".", "-") for s in symbols]
    prices = yf.download(yf_symbols, period=period, auto_adjust=True, progress=False)["Close"]
    log_ret = np.log(prices / prices.shift(1)).dropna()
    
    corr = log_ret.corr()
    dist = np.sqrt(2 * (1 - corr.clip(-1, 1)))
    condensed = squareform(dist.values)
    Z = linkage(condensed, method="ward")
    
    if n_clusters is None:
        # Método del codo: elegir K donde la aceleración de la fusión es máxima
        diffs = np.diff(Z[:, 2])
        n_clusters = len(symbols) - int(np.argmax(diffs)) - 1
        n_clusters = max(2, min(n_clusters, len(symbols) // 2))
    
    labels = fcluster(Z, t=n_clusters, criterion="maxclust")
    clusters = {sym: int(lbl) for sym, lbl in zip(corr.columns, labels)}
    
    # Resumen por cluster: qué activos están juntos y cuán correlacionados
    summary = {}
    for cid in sorted(set(clusters.values())):
        members = [s for s, c in clusters.items() if c == cid]
        if len(members) > 1:
            sub = corr.loc[members, members]
            mask = np.triu(np.ones(sub.shape, dtype=bool), k=1)
            avg_corr = float(sub.values[mask].mean())
        else:
            avg_corr = 1.0
        summary[cid] = {"symbols": members, "avg_intra_correlation": round(avg_corr, 3)}
    
    return {
        "n_clusters": n_clusters,
        "clusters": clusters,
        "cluster_summary": summary,
        "correlation_matrix": corr.round(3).to_dict(),
        "linkage_matrix": Z.tolist(),   # para dendrograma en frontend
    }
```

### Endpoint sugerido

```
GET /api/snapshots/current/clustering/
```

Lee los símbolos del snapshot actual, corre `run_clustering`, retorna el JSON. Parámetro opcional `?n_clusters=3`.

### Visualización en el frontend

Dos opciones complementarias:

1. **Heatmap de correlaciones** — grilla N×N coloreada de rojo (ρ=1) a azul (ρ=-1). Reordenada según el dendrograma para que los activos similares queden juntos.

2. **Dendrograma** — árbol de fusiones usando la `linkage_matrix`. Permite ver visualmente a qué altura se separan los clusters. La librería `d3-hierarchy` o una implementación en SVG con Recharts puede renderizarlo.

La opción más simple para MVP: heatmap con colores usando una tabla CSS + gradiente. El dendrograma requiere D3 o una librería dedicada.

---

## Interpretación de resultados

| Situación | Qué significa |
|-----------|--------------|
| Todos los activos en 1 cluster | Portfolio no diversificado — se mueven juntos |
| Cluster grande + activos sueltos | Los sueltos son los verdaderos diversificadores |
| ρ > 0.8 entre dos activos | Prácticamente redundantes — uno aporta poco |
| ρ < 0.2 entre clusters | Buena diversificación entre esos grupos |
| Activo con ρ negativa | Cobertura natural (ej: oro vs acciones en crisis) |

---

## Dependencias

```
# backend/requirements.txt
scipy        # linkage, fcluster, squareform — ya puede estar instalado via numpy
scikit-learn # KMeans, silhouette_score — si se usa el enfoque K-Means
```

`scipy` generalmente ya está disponible en entornos con `numpy`. `scikit-learn` requiere instalación explícita.

---

## Limitaciones a tener en cuenta

- **Correlaciones no son estables en el tiempo** — calculadas sobre 2 años pueden no reflejar el comportamiento en crisis. Considerar ventanas rodantes o correlaciones condicionales.
- **N pequeño** — con menos de 10 activos el clustering tiene poco valor; con menos de 5, directamente leer la matriz de correlación es más útil.
- **Correlación ≠ causalidad** — dos activos pueden estar correlacionados por un factor común (ej: dólar) sin relación directa entre ellos.
- **yfinance puede fallar** — aplicar el mismo patrón de timeout y ticker normalization que el resto de los scripts.
