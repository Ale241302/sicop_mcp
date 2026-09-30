# Decisión — exposición de `inhibiciones` en la API/MCP

- **Fecha:** 2026-09-30
- **Conjunto:** `inhibiciones` (`FuncionariosInhibicion.csv` → `sicop_inhibiciones`)
- **Marco:** Ley 8968 (Protección de la Persona frente al tratamiento de sus datos
  personales), principio de **finalidad** y **minimización**; Ley 8131 / Decreto
  40199-MP (datos abiertos del Observatorio).
- **Estado:** vigente.

## El dato

`inhibiciones` es, según la skill `sicop-extraccion` (§11), **el conjunto más
sensible**: contiene **personas nombradas** (funcionarios públicos con
inhibición), con `NOM_FUNCIONARIO`, `CED_FUNCIONARIO`, institución y fechas. Los
ZIP vienen del Observatorio de Hacienda (datos abiertos), pero **un dato público
no es automáticamente una fuente usable de forma masiva** para cualquier fin.

## La decisión

1. **El dato se conserva completo en la base** (bronze + core). No se borra ni se
   anonimiza en origen: la trazabilidad completa es necesaria para auditar la
   contratación.
2. **La API REST y el MCP NO devuelven por defecto** el nombre ni la cédula del
   funcionario. La respuesta los enmascara:
   - `NOM_FUNCIONARIO` → `DATO_PERSONAL_RESTRINGIDO`
   - `CED_FUNCIONARIO` → forma parcial (3 primeros + 2 últimos dígitos)
3. **No hay búsqueda libre por nombre de funcionario.** Se retiró
   `NOM_FUNCIONARIO` de los campos filtrables. El uso previsto es **dirigido por
   institución** (`CED_INSTITUCION`) o por cédula puntual, no barrido por persona.
4. **Se puede habilitar la exposición completa solo por decisión expresa**, vía
   variable de entorno `SICOP_INHIBICIONES_NOMBRES=1` (por ejemplo, para un
   análisis interno autorizado). Por defecto está en `0`.
5. **Gate de política P6** (`sicop_mcp/sicop/enforcement.py`): si la API dejara de
   minimizar sin una decisión expresa, `pruebas_politica` falla. La decisión queda
   así **ejecutable y verificable**, no solo escrita.

## Alternativas consideradas y descartadas

| Alternativa | Por qué no |
|---|---|
| Servir el consolidado completo sin cambios | Barrido universal de personas nombradas: excede la finalidad del servicio. |
| Borrar `NOM_FUNCIONARIO`/`CED_FUNCIONARIO` de la base | Se pierde la trazabilidad que permite cruzar una inhibición puntual y auditar el proceso; el análisis de conflictos es legítimo y dirigido. |
| Dejar todo como estaba y solo documentar | La skill pide una decisión; sin control ejecutable, la próxima edición del serializer puede revertirla en silencio. |

## Alcance y límite

Esta es una decisión de **minimización técnica** para una herramienta de uso
interno y dirigido. **No es una opinión jurídica.** Si el sistema se expone a
terceros, se publica, o se comercializa, aplica la cláusula 5.d de SICOP y el
análisis de la skill §1 y §11 — **consulta de abogado, no interpretación propia.**

## Regla operativa

> Consultar la situación de un funcionario o proveedor puntual, con un fin
> documentado, es defendible. **Barrer el padrón completo, no.**

## Cómo se verifica

```bash
python manage.py test sicop.tests_gate.PruebasPoliticaTest
python manage.py shell -c "from sicop.enforcement import pruebas_politica; print(pruebas_politica('doc'))"
# P6 → True (nombre+cedula enmascarados por defecto)
```

Archivos que implementan la decisión:
- `sicop_mcp/config/settings.py` → `SICOP_INHIBICIONES_NOMBRES`
- `sicop_mcp/sicop/api/serializers.py` → `_inhibiciones_serializer` / `_mask_cedula`
- `sicop_mcp/sicop/api/views.py` → `FILTERABLE["SicopInhibiciones"]`
- `sicop_mcp/sicop/enforcement.py` → prueba de política `p6_inhibiciones_minimizadas`
