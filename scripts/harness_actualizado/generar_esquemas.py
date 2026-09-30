# -*- coding: utf-8 -*-
"""Genera esquemas.json: el embrion de catalogo_campo.
Cabeceras completas de los 25 conjuntos + tipo inferido, llenado y cardinalidad
medidos sobre una muestra. Pesa KB y desbloquea el diseno sin mover datos."""
import csv, sys, glob, os, json, re
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
csv.field_size_limit(10**9)

B = r"C:\DeepSeek Harness\salida"
MUESTRA = 50000          # filas por archivo para medir llenado/cardinalidad
OUT = r"C:\Users\alvar\Downloads\_entrega\esquemas.json"

RX_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")
RX_NUM   = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")
RX_DIG   = re.compile(r"^\d+$")

# trampas ya verificadas, para sembrar el catalogo
TRAMPAS = {
    ("ordenes_pedido", "SECUENCIA"): "ENUM (98% en '00'), NO identifica linea. Usar LINEA_ORD_PEDIDO",
    ("ordenes_pedido", "TOTAL_ORDEN"): "Total de la ORDEN replicado en cada linea. Sumar en crudo infla ~3x. 4 outliers >1e12",
    ("ordenes_pedido", "MONEDA_ORDEN"): "5 monedas. En 2026: 61.941 ordenes CRC y 42.131 USD. Sumar sin convertir divide por ~510 a importadores",
    ("ordenes_pedido", "LINEA_ORD_PEDIDO"): "LA clave de linea junto a NRO_ORDEN",
    ("ordenes_pedido", "FECHA_ELABORACION_ORDEN"): "El anio del hecho. NO usar el anio del zip",
    ("lineas_cartel", "CODIGO_IDENTIFICACION"): "El codigo de producto del CARTEL: 16 digitos (99,7%). La oferta usa 24. Puente = prefijo[:16], NUNCA igualdad",
    ("lineas_cartel", "NUMERO_PARTIDA"): "Parte de la clave. Sin esto (NRO_SICOP, NUMERO_LINEA) NO es unica",
    ("lineas_cartel", "NUMERO_LINEA"): "Se llama NRO_LINEA en ofertadas/adjudicadas. Ceros a la izquierda o '1.0'. Normalizar a entero-string",
    ("lineas_ofertadas", "NRO_LINEA"): "Se llama NUMERO_LINEA en cartel. Normalizar",
    ("lineas_ofertadas", "CODIGO_PRODUCTO"): "24 digitos = UNSPSC(8)+CATALOGO(8)+correlativo(8). El correlativo NO identifica producto",
    ("lineas_ofertadas", "CODIGO_PRODUCTO_CL"): "16 digitos = codigo_producto[:16]. Anidamiento verificado 96,9%",
    ("lineas_ofertadas", "NRO_OFERTA"): "No trae cedula. Unir con ofertas por NRO_SICOP+NRO_OFERTA",
    ("lineas_contratadas", "DESC_PRODUCTO"): "Trae 'Marca X Modelo Y' en 99,6%. Regex CASE-SENSITIVE obligatorio (re.I da falsos positivos)",
    ("lineas_recibidas", "desc_producto"): "Trae 'Marca X Modelo Y' en 99,6%. Case-sensitive",
    ("proveedores", "TAMAÑO_PROVEEDOR"): "Lleva N con virgulilla. Buscar 'TAMANO' devuelve 'no existe'",
    ("adjudicaciones_firme", "DESIERTO"): "Y/N, no S/N. 242.918 N contra 4 Y: NO sirve para medir desiertos",
    ("recursos", "PROSPERO"): "Los 334 sin desenlace cuentan como N. Filtrar RESULTADO != '' antes de calcular tasas",
    ("sanciones_registro", "INICIO_SANCION"): "Formato DDMMYYYY pegado. Cruzar con FINAL_SANCION para vigencia",
    ("contratos", "TIPO_MODIFICACION"): "34% modificados. La modificacion NO se mide en lineas_contratadas.monto_disminuido (6 filas de 102.128)",
}

def tipo_de(vals):
    v = [x for x in vals if x]
    if not v: return "vacio"
    if all(RX_FECHA.match(x) for x in v[:200]): return "fecha"
    if all(RX_NUM.match(x) for x in v[:200]):
        largos = {len(x) for x in v[:200] if RX_DIG.match(x)}
        if largos and largos <= {8, 16, 24}:
            return f"codigo({'/'.join(str(l) for l in sorted(largos))})"
        return "decimal" if any("." in x for x in v[:200]) else "entero"
    if all(x.upper() in ("S", "N", "Y", "SI", "NO", "") for x in v[:200]): return "binario"
    return "texto"

def main():
    archivos = defaultdict(list)
    for p in sorted(glob.glob(os.path.join(B, "*.csv"))):
        n = os.path.basename(p)
        base = n.rsplit("_", 1)[0] if n[-8:-4].isdigit() else n[:-4]
        archivos[base].append(p)

    esquemas = {}
    for base, paths in sorted(archivos.items()):
        p = sorted(paths)[-1]          # el mas reciente
        try:
            with open(p, encoding="utf-8", errors="replace", newline="") as f:
                r = csv.DictReader(f)
                cab = r.fieldnames or []
                vals = defaultdict(list)
                distintos = defaultdict(set)
                llenos = Counter()
                n = 0
                for row in r:
                    if n >= MUESTRA: break
                    n += 1
                    for c in cab:
                        v = (row.get(c) or "").strip()
                        if v:
                            llenos[c] += 1
                            if len(vals[c]) < 300: vals[c].append(v)
                            if len(distintos[c]) < 5000: distintos[c].add(v)
        except Exception as e:
            esquemas[base] = {"error": str(e)}
            continue

        campos = []
        for c in cab:
            card = len(distintos[c])
            campos.append({
                "campo": c,
                "tipo": tipo_de(vals[c]),
                "llenado_pct": round(100.0 * llenos[c] / max(n, 1), 1),
                "cardinalidad": card if card < 5000 else ">=5000",
                "ejemplos": vals[c][:3],
                "trampa": TRAMPAS.get((base, c)),
            })
        esquemas[base] = {
            "archivos_por_anio": len(paths),
            "filas_muestreadas": n,
            "n_columnas": len(cab),
            "campos": campos,
        }
        print(f"{base:28s} {len(cab):>3} columnas · {n:,} filas muestreadas")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "generado": "2026-08-25",
            "fuente": "C:\\DeepSeek Harness\\salida",
            "nota": "llenado y cardinalidad medidos sobre muestra de hasta "
                    f"{MUESTRA:,} filas del archivo mas reciente de cada conjunto. "
                    "Los conteos totales estan en manifiesto.json",
            "conjuntos": esquemas,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n-> {OUT}  ({os.path.getsize(OUT)/1024:.1f} KB)")

if __name__ == "__main__":
    main()
