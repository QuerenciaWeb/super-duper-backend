"""
Predicción de consumo y reposición de insumos.

Idea: el consumo diario de cada insumo se estima a partir de las ventas (DetallePedido):
  - ventas directas del insumo, más
  - ventas de platos × cantidad de ese insumo en la receta (RecetaInsumo).
Con esa serie diaria se calcula nivel reciente, tendencia (sube/baja) y estacionalidad por día de la semana,
se proyecta la demanda y se sugiere cuánto pedir. Sin librerías externas: con pocos meses de datos
un modelo simple y explicable rinde mejor que uno complejo.
"""
import math
import os
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional

from django.db.models import Sum, Min
from django.utils import timezone

from modelos.models import Producto, Pedido, DetallePedido, RecetaInsumo, EntradaProducto, Notificacion

MIN_DIAS_DATOS = 7        # menos que esto: no se predice
MIN_DIAS_ESTACIONAL = 28  # desde aquí se usa estacionalidad semanal y tendencia
VENTANA_TENDENCIA = 14
MAX_DIAS_SIMULACION = 365


def _entero_env(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


def _calcular_serie(serie: Dict[date, float], hoy: date, dias_efectivos: int):
    """Devuelve (nivel_diario, factores_semana[7], tendencia, ratio_tendencia)."""
    dias = [hoy - timedelta(days=i) for i in range(dias_efectivos, 0, -1)]  # ayer hacia atrás
    valores = [float(serie.get(d, 0)) for d in dias]
    media = sum(valores) / len(valores)

    factores = [1.0] * 7
    tendencia, ratio = "ESTABLE", 1.0
    nivel = media

    if dias_efectivos >= MIN_DIAS_ESTACIONAL:
        if media > 0:
            por_dia = defaultdict(list)
            for d, v in zip(dias, valores):
                por_dia[d.weekday()].append(v)
            for w in range(7):
                if por_dia[w]:
                    factores[w] = (sum(por_dia[w]) / len(por_dia[w])) / media
            norm = sum(factores) / 7
            factores = [f / norm for f in factores] if norm > 0 else [1.0] * 7

        reciente = valores[-VENTANA_TENDENCIA:]
        previo = valores[-2 * VENTANA_TENDENCIA:-VENTANA_TENDENCIA]
        m_rec = sum(reciente) / len(reciente)
        m_prev = sum(previo) / len(previo) if previo else 0
        if m_prev > 0:
            ratio = m_rec / m_prev
        elif m_rec > 0:
            ratio = 1.5
        ratio = max(0.5, min(1.5, ratio))
        if ratio > 1.1:
            tendencia = "SUBE"
        elif ratio < 0.9:
            tendencia = "BAJA"
        nivel = m_rec if tendencia == "SUBE" else 0.6 * m_rec + 0.4 * media  # pesa más lo reciente

    return nivel, factores, tendencia, ratio


def calcular_prediccion(serie: Dict[date, float], hoy: date, dias_efectivos: int, stock: int,
                        horizonte: int = 7, lead_time: int = 3, seguridad: float = 0.2) -> dict:
    """
    Lógica pura (sin base de datos).
      serie          consumo por fecha (unidades del insumo)
      dias_efectivos días de historial con operación del negocio (≤ ventana pedida)
      horizonte      días de cobertura deseada después de que llegue el pedido
      lead_time      días que tarda el proveedor en entregar
      seguridad      colchón (0.2 = 20 %)
    """
    if dias_efectivos < MIN_DIAS_DATOS:
        return {"riesgo": "SIN_DATOS", "tendencia": "SIN_DATOS", "consumo_diario": None,
                "demanda_horizonte": None, "dias_restantes": None, "fecha_agotamiento": None,
                "cantidad_sugerida": None}

    nivel, factores, tendencia, _ = _calcular_serie(serie, hoy, dias_efectivos)

    def previsto(k: int) -> float:  # día k a partir de hoy
        return nivel * factores[(hoy + timedelta(days=k)).weekday()]

    demanda_horizonte = sum(previsto(k) for k in range(horizonte))
    demanda_cobertura = sum(previsto(k) for k in range(lead_time + horizonte))
    sugerida = max(0, math.ceil(demanda_cobertura * (1 + seguridad) - stock))

    if nivel <= 0:
        dias_restantes = None
    elif stock <= 0:
        dias_restantes = 0.0
    else:
        acumulado, dias_restantes = 0.0, None
        for k in range(MAX_DIAS_SIMULACION):
            consumo = previsto(k)
            if acumulado + consumo >= stock:
                dias_restantes = k + (stock - acumulado) / consumo if consumo > 0 else float(k)
                break
            acumulado += consumo

    if nivel <= 0:
        riesgo = "SIN_CONSUMO"
    elif dias_restantes is None:
        riesgo = "OK"  # alcanza para más de un año
    elif dias_restantes <= lead_time:
        riesgo = "CRITICO"
    elif dias_restantes <= lead_time + horizonte:
        riesgo = "ALERTA"
    else:
        riesgo = "OK"

    fecha_agot = (hoy + timedelta(days=math.floor(dias_restantes))).isoformat() if dias_restantes is not None else None
    return {
        "riesgo": riesgo,
        "tendencia": tendencia,
        "consumo_diario": round(nivel, 2),
        "demanda_horizonte": round(demanda_horizonte, 1),
        "dias_restantes": round(dias_restantes, 1) if dias_restantes is not None else None,
        "fecha_agotamiento": fecha_agot,
        "cantidad_sugerida": sugerida,
    }


def _obtener_consumos(hoy: date, historial: int):
    """Serie diaria de consumo por insumo + días efectivos de historial."""
    desde = hoy - timedelta(days=historial)
    pedidos_validos = Pedido.objects.exclude(estado="Cancelado").filter(fecha__gte=desde, fecha__lt=hoy)

    primera = pedidos_validos.aggregate(m=Min("fecha"))["m"]
    dias_efectivos = (hoy - primera).days if primera else 0
    dias_efectivos = min(dias_efectivos, historial)

    insumos_ids = set(Producto.objects.filter(es_insumo=True).values_list("dni_producto", flat=True))
    recetas = defaultdict(list)
    for r in RecetaInsumo.objects.values("plato_id", "insumo_id", "cantidad"):
        recetas[r["plato_id"]].append((r["insumo_id"], r["cantidad"]))

    ventas = (
        DetallePedido.objects.filter(pedido__in=pedidos_validos)
        .values("producto_id", "pedido__fecha")
        .annotate(total=Sum("cantidad"))
    )
    series: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for v in ventas:
        fecha, total, pid = v["pedido__fecha"], v["total"] or 0, v["producto_id"]
        if pid in insumos_ids:
            series[pid][fecha] += total
        for insumo_id, cant in recetas.get(pid, []):
            series[insumo_id][fecha] += total * cant
    return series, dias_efectivos


def predecir_stock(horizonte: int = 7, historial: int = 56, lead_time: Optional[int] = None,
                   seguridad: float = 0.2) -> List[dict]:
    """Predicción para todos los insumos activos, ordenada por urgencia."""
    lead_time = lead_time if lead_time is not None else _entero_env("LEAD_TIME_DIAS", 3)
    hoy = timezone.localdate()
    series, dias_efectivos = _obtener_consumos(hoy, historial)

    ultimo_proveedor = {}
    for e in EntradaProducto.objects.select_related("proveedor").order_by("fechaEntrada", "idEntrada"):
        ultimo_proveedor[e.producto_id] = e.proveedor.nombre

    resultado = []
    for p in Producto.objects.filter(es_insumo=True).select_related("categoria").order_by("nombre"):
        pred = calcular_prediccion(series.get(p.dni_producto, {}), hoy, dias_efectivos, p.stock,
                                   horizonte, lead_time, seguridad)
        resultado.append({
            "dni_producto": str(p.dni_producto),
            "nombre": p.nombre,
            "categoria_nombre": p.categoria.nombre if p.categoria else None,
            "stock": p.stock,
            "proveedor_habitual": ultimo_proveedor.get(p.dni_producto),
            **pred,
        })

    orden = {"CRITICO": 0, "ALERTA": 1, "OK": 2, "SIN_CONSUMO": 3, "SIN_DATOS": 4}
    resultado.sort(key=lambda r: (orden[r["riesgo"]],
                                  r["dias_restantes"] if r["dias_restantes"] is not None else 9999,
                                  r["nombre"]))
    return resultado


def notificar_riesgos(predicciones: List[dict]) -> int:
    """Crea notificaciones (una por producto y día) para insumos en riesgo CRITICO."""
    creadas = 0
    hoy = timezone.localdate()
    for p in predicciones:
        if p["riesgo"] != "CRITICO":
            continue
        dias = p["dias_restantes"]
        cuando = "ya está agotado" if not dias else f"se agotaría en ~{dias:g} días"
        _, nueva = Notificacion.objects.get_or_create(
            mensaje=(f"Reposición urgente: {p['nombre']} (código {p['dni_producto']}) {cuando}. "
                     f"Sugerido pedir {p['cantidad_sugerida']} u."),
            fecha=hoy,
        )
        creadas += int(nueva)
    return creadas
