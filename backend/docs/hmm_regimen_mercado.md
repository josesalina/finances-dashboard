# Hidden Markov Model — Detección de Régimen de Mercado

## Qué problema resuelve

El `semaforo_mercado.py` actual clasifica el mercado con reglas hardcodeadas: si VIX > 25 → penalizar, si SPY ret_1d < -1% → penalizar, etc. Estas reglas fueron calibradas manualmente y no se adaptan a cambios de contexto.

Un HMM aprende automáticamente qué combinaciones de observaciones (retornos, VIX, spreads) corresponden a cada régimen de mercado, asignando probabilidades en vez de umbrales binarios. El resultado reemplaza o enriquece la lógica del semáforo con una señal estadísticamente fundamentada.

---

## Concepto central

### Qué es un HMM

Un Hidden Markov Model tiene dos capas:

- **Estados ocultos** `S ∈ {S1, S2, ..., Sk}` — los regímenes que queremos detectar (bull, bear, alta volatilidad). No se observan directamente.
- **Observaciones** `O_t` — lo que sí medimos cada día (retorno de SPY, nivel de VIX, spread de crédito). Cada estado genera observaciones con una distribución característica.

El modelo aprende tres matrices:
- `π` — probabilidad inicial de cada estado
- `A` — matriz de transición: P(S_{t+1} | S_t), qué tan probable es pasar de un régimen a otro
- `B` — distribución de emisión: P(O_t | S_t), qué observaciones genera cada estado

### Gaussian HMM (el más usado en finanzas)

Cada estado emite observaciones multivariadas con distribución Normal:

```
O_t | S_t=k  ~  N(μ_k, Σ_k)
```

Donde `μ_k` es el vector de medias (retorno medio, VIX medio) y `Σ_k` es la covarianza del estado k. El algoritmo de Baum-Welch (EM) ajusta todos los parámetros sin necesidad de etiquetas.

---

## Regímenes esperados

Con 3 estados y las features propuestas, el modelo típicamente converge a:

| Estado | Retorno SPY | VIX | Spread crédito | Interpretación |
|--------|-------------|-----|----------------|----------------|
| S1 | Positivo moderado | Bajo (< 15) | Bajo | Bull market / calma |
| S2 | Cercano a cero | Medio (15-25) | Moderado | Lateral / incertidumbre |
| S3 | Negativo | Alto (> 25) | Elevado | Bear / crisis |

El modelo **no sabe** cuál es cuál — después del entrenamiento hay que etiquetar los estados manualmente mirando sus parámetros μ_k. El estado con μ_retorno más alto = bull.

---

## Features de entrada (observaciones)

Todas ya disponibles en `semaforo_mercado.py` via `get_market_data()`:

| Feature | Cómo calcularla | Por qué |
|---------|----------------|---------|
| `spy_ret_5d` | Retorno de SPY a 5 días | Momentum de corto plazo |
| `spy_ret_21d` | Retorno de SPY a 21 días | Tendencia mensual |
| `vix_level` | Precio de cierre de ^VIX | Volatilidad implícita del mercado |
| `vix_change_5d` | Cambio de VIX en 5 días | Aceleración del miedo |
| `hy_spread` | Retorno de HYG (high yield ETF) | Apetito por riesgo crediticio |
| `yield_curve` | TLT ret_5d - SHY ret_5d | Pendiente de curva de tasas |

Normalizar todas las features antes de entrenar (z-score o MinMaxScaler).

---

## Implementación

### Script sugerido: `backend/scripts/analisis_regimen.py`

```python
import yfinance as yf
import numpy as np
import pandas as pd
from hmmlearn import hmm

TICKERS = {
    "spy": "SPY",
    "vix": "^VIX",
    "hyg": "HYG",   # high yield — proxy de spread de crédito
    "tlt": "TLT",   # bonos largo plazo
    "shy": "SHY",   # bonos corto plazo
}

def _build_features(prices: pd.DataFrame) -> pd.DataFrame:
    spy = prices["SPY"]
    vix = prices["^VIX"]

    features = pd.DataFrame(index=prices.index)
    features["spy_ret_5d"]    = spy.pct_change(5)
    features["spy_ret_21d"]   = spy.pct_change(21)
    features["vix_level"]     = vix
    features["vix_change_5d"] = vix.pct_change(5)
    features["hy_spread"]     = prices["HYG"].pct_change(5)
    features["yield_curve"]   = prices["TLT"].pct_change(5) - prices["SHY"].pct_change(5)

    return features.dropna()


def _label_states(model: hmm.GaussianHMM, feature_cols: list) -> dict:
    """Asignar etiquetas legibles a los estados según su μ de retorno."""
    spy_idx = feature_cols.index("spy_ret_5d")
    means = model.means_[:, spy_idx]
    order = np.argsort(means)[::-1]   # mayor retorno primero
    labels = {}
    names = ["BULL", "LATERAL", "BEAR"] if len(order) == 3 else [f"S{i}" for i in range(len(order))]
    for rank, state_id in enumerate(order):
        labels[int(state_id)] = names[rank]
    return labels


def run_hmm_regimen(n_states: int = 3, period: str = "5y") -> dict:
    """
    Descarga datos históricos, entrena HMM Gaussiano y retorna el régimen actual
    con probabilidades de transición.

    Returns dict con:
      - current_regime: "BULL" | "LATERAL" | "BEAR"
      - current_probs: {regime: probability}
      - transition_matrix: P(S_{t+1} | S_t) con etiquetas legibles
      - state_params: μ y σ de cada estado para cada feature
      - regime_history: [{date, regime}] — últimos 252 días
    """
    raw = yf.download(
        list(TICKERS.values()), period=period,
        auto_adjust=True, progress=False
    )["Close"]

    features_df = _build_features(raw)
    feature_cols = features_df.columns.tolist()

    # Normalizar (z-score)
    mu  = features_df.mean()
    std = features_df.std().replace(0, 1)
    X   = ((features_df - mu) / std).values

    model = hmm.GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(X)

    state_labels = _label_states(model, feature_cols)

    # Secuencia de estados histórica
    hidden_states = model.predict(X)
    state_probs   = model.predict_proba(X)

    # Estado actual (último día)
    current_state     = int(hidden_states[-1])
    current_regime    = state_labels[current_state]
    current_probs_raw = state_probs[-1]
    current_probs     = {state_labels[i]: round(float(p), 4)
                         for i, p in enumerate(current_probs_raw)}

    # Matriz de transición con etiquetas
    trans = {}
    for i, row in enumerate(model.transmat_):
        from_label = state_labels[i]
        trans[from_label] = {state_labels[j]: round(float(p), 4)
                             for j, p in enumerate(row)}

    # Parámetros de cada estado (μ y σ por feature)
    state_params = {}
    for sid, label in state_labels.items():
        state_params[label] = {
            col: {
                "mean":  round(float(model.means_[sid, ci] * std[col] + mu[col]), 6),
                "std":   round(float(np.sqrt(model.covars_[sid, ci, ci]) * std[col]), 6),
            }
            for ci, col in enumerate(feature_cols)
        }

    # Historial de régimen — últimos 252 días
    history_index = features_df.index[-252:]
    history_states = hidden_states[-252:]
    regime_history = [
        {"date": str(d.date()), "regime": state_labels[int(s)]}
        for d, s in zip(history_index, history_states)
    ]

    return {
        "n_states":          n_states,
        "current_regime":    current_regime,
        "current_probs":     current_probs,
        "transition_matrix": trans,
        "state_params":      state_params,
        "regime_history":    regime_history,
    }


if __name__ == "__main__":
    import json, sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(json.dumps(run_hmm_regimen(n_states=n), indent=2))
```

---

## Integración con el semáforo existente

### Opción A — Reemplazo parcial (recomendada)

Reemplazar la función `semaforo_principal` de `semaforo_mercado.py` para que use el régimen HMM como señal primaria, manteniendo el resto de los ajustes (energía, tasas, etc.):

```python
# En semaforo_mercado.py, dentro de semaforo_principal():
regimen = run_hmm_regimen()
base_code = {
    "BULL":    "GO",
    "LATERAL": "PARTIAL",
    "BEAR":    "WAIT",
}.get(regimen["current_regime"], "PARTIAL")

# Sobrescribir a ABORT solo si probabilidad bear > 80%
if regimen["current_probs"].get("BEAR", 0) > 0.80:
    base_code = "ABORT"
```

### Opción B — Capa adicional (más conservadora)

Mantener el semáforo actual intacto y agregar el régimen HMM como metadata extra en el output de `semaforo_raw`:

```python
# En run_semaforo() de script_runner.py:
regimen = run_hmm_regimen()
result["regimen_hmm"] = regimen
```

El frontend puede mostrarlo como información adicional sin que afecte la decisión del semáforo.

---

## Endpoint sugerido

```
GET /api/regimen/
```

Retorna el régimen actual con probabilidades y el historial de los últimos 252 días. Parámetro opcional `?n_states=3`.

Nueva página o sección en `/semaforos` mostrando:
- Badge del régimen actual (BULL / LATERAL / BEAR) con barra de probabilidades
- Gráfico de área apilada con el historial de regímenes (colores: verde/amarillo/rojo)
- Matriz de transición como tabla: "desde BULL, 92% de probabilidad de seguir en BULL mañana"

---

## Dependencias

```
# backend/requirements.txt
hmmlearn    # Gaussian HMM — pip install hmmlearn
```

`hmmlearn` depende de `scikit-learn` y `numpy`, ya disponibles.

---

## Limitaciones importantes

**No estacionariedad:** el modelo entrenado sobre datos de 2020-2025 puede no reconocer regímenes futuros con características nuevas (ej: stagflación, tasas muy altas por mucho tiempo). Mitigación: reentrenar con ventana rodante cada vez que corre el semáforo (ya es el flujo del script).

**Etiquetado manual necesario:** el HMM aprende estados numéricos (0, 1, 2), no "bull/bear". Hay que inspeccionar los parámetros μ_k para asignar etiquetas. La función `_label_states` lo hace automáticamente por retorno medio, pero puede fallar si los estados son muy similares.

**Sensibilidad al número de estados:** con 2 estados el modelo es estable pero pierde matices; con 4+ tiende a sobreajustar con pocos activos. 3 estados es el balance habitual en literatura financiera.

**Tiempo de entrenamiento:** Baum-Welch con 200 iteraciones sobre 5 años de datos (~1250 días × 6 features) tarda ~1-3 segundos. Aceptable para el flujo del semáforo que ya hace llamadas a yfinance de 2-5 segundos.

**Overfitting silencioso:** el modelo siempre converge — no hay un error obvio cuando sobreajusta. Validar mirando si el régimen histórico tiene sentido (S&P cayendo en estado "BULL" = problema).
