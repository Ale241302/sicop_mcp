# Deploy de sicop_mcp al VPS (187.77.218.102) con nginx + Cloudflare

## 1. Cloudflare DNS — crear estos records en `vlinte.work`

En Cloudflare → `vlinte.work` → **DNS → Records → Add record** (0 de 200 usados):

| Type | Name | Content | Proxy | Nota |
|---|---|---|---|---|
| A | `@` | `187.77.218.102` | **Proxied** (nube naranja) | el dominio raíz |
| A | `www` | `187.77.218.102` | Proxied | o CNAME `www` → `vlinte.work` |
| A | `sicop` | `187.77.218.102` | Proxied | **subdominio de esta app** |

El aviso de email (`@vlinte.work` MX/SPF/DKIM) **se ignora** si no usás correo en ese dominio.

## 2. Puertos — sin colisión con lo que ya corre en el VPS

El compose de sicop_mcp usa **`8400:8000`** (django). No toca 80/443 del nginx compartido.

Puertos ya ocupados en el VPS (no usar):
`80 · 443 (mwt-nginx) · 8000 (mwt-django) · 8100 (consola-mwt-one-django) · 8200 (faberloom-api) · 8300 (mundial-api) · 3100 (mwt-builder-nginx) · 3101 (consola-frontend) · 3300 (mundial-web) · 5679 (n8n) · 8888 (paperless) · 9100/9101 (minio) · 5433-5436 (postgres) · 6379/6380/6382 (redis)`

## 3. Subir el repo al VPS y desplegar (mismo patrón que consola-mwt-one)

```bash
ssh -p 2222 root@187.77.218.102
cd /opt
git clone https://github.com/Ale241302/sicop_mcp.git
cd /opt/sicop_mcp
docker compose up -d --build        # django en 8400 + postgres + redis + celery
docker compose exec django python manage.py migrate
# (opcional) montar /data/salidas y cargar: docker compose exec django python manage.py load_sicop --sync
```

## 4. Nginx compartido (no choca con los demás)

1. Copiar `deploy/nginx-sicop.conf` al nginx compartido del VPS (mwt-nginx).
2. Probar y recargar:
```bash
docker exec mwt-nginx nginx -t && docker exec mwt-nginx nginx -s reload
```
3. Si el origen está detrás de Cloudflare: usa **Cloudflare Full (strict)** y genera certbot:
```bash
docker exec mwt-nginx certbot --nginx -d sicop.vlinte.work   # o certbot del host
```

## 5. Verificar

```bash
curl -sI http://127.0.0.1:8400/api/v1/resumen/ | head -1   # 200 local
curl -sI https://sicop.vlinte.work/api/v1/resumen/ | head -1 # 200 vía Cloudflare
```

## 6. Datos en el VPS

La base local (~49M filas) no viaja en git. Opciones:
- **pg_dump** de la base local → restaurar en el postgres del VPS.
- O volver a correr `load_sicop --sync` con `Salidas/` montado (4-6 h).
- Para arrancar el panel/API vacío funciona igual; los datos se cargan cuando los montes.
