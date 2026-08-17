"""
Adaptador Cloudflare - DNS, Access, Tunnels, WAF.
"""

import httpx
import structlog

logger = structlog.get_logger()


class CloudflareAdapter:
    """Adaptador para Cloudflare API."""

    def __init__(self, config: dict):
        self.config = config
        self.api_token = config.get("CLOUDFLARE_API_TOKEN")
        self.account_id = config.get("CLOUDFLARE_ACCOUNT_ID")
        self.zone_id = config.get("CLOUDFLARE_ZONE_ID")
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def close(self):
        await self.client.aclose()

    async def _request(self, method: str, endpoint: str, json: dict = None, params: dict = None) -> dict:
        """Realizar petición a Cloudflare API."""
        url = f"{self.base_url}{endpoint}"
        resp = await self.client.request(method, url, json=json, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise Exception(f"Cloudflare API error: {data.get('errors')}")
        return data.get("result", data)

    # =========================================================================
    # DNS MANAGEMENT
    # =========================================================================

    async def list_dns_records(self, zone_id: str = None, type: str = None, name: str = None) -> list[dict]:
        """Listar registros DNS."""
        zone = zone_id or self.zone_id
        params = {}
        if type:
            params["type"] = type
        if name:
            params["name"] = name

        result = await self._request("GET", f"/zones/{zone}/dns_records", params=params)
        return result if isinstance(result, list) else result.get("result", [])

    async def create_dns_record(
        self,
        zone_id: str = None,
        type: str = "A",
        name: str = "",
        content: str = "",
        ttl: int = 300,
        proxied: bool = False,
        comment: str = "",
    ) -> dict:
        """Crear registro DNS."""
        zone = zone_id or self.zone_id
        data = {
            "type": type,
            "name": name,
            "content": content,
            "ttl": ttl,
            "proxied": proxied,
            "comment": comment,
        }
        return await self._request("POST", f"/zones/{zone}/dns_records", json=data)

    async def update_dns_record(self, record_id: str, zone_id: str = None, **kwargs) -> dict:
        """Actualizar registro DNS."""
        zone = zone_id or self.zone_id
        return await self._request("PUT", f"/zones/{zone}/dns_records/{record_id}", json=kwargs)

    async def delete_dns_record(self, record_id: str, zone_id: str = None) -> bool:
        """Eliminar registro DNS."""
        zone = zone_id or self.zone_id
        await self._request("DELETE", f"/zones/{zone}/dns_records/{record_id}")
        return True

    # =========================================================================
    # CLOUDFLARE ACCESS (Zero Trust)
    # =========================================================================

    async def list_access_applications(self) -> list[dict]:
        """Listar aplicaciones Access."""
        result = await self._request("GET", f"/accounts/{self.account_id}/access/apps")
        return result if isinstance(result, list) else result.get("result", [])

    async def create_access_application(self, name: str, domain: str, policies: list[dict] = None) -> dict:
        """Crear aplicación Access."""
        data = {
            "name": name,
            "domain": domain,
            "type": "self_hosted",
            "session_duration": "24h",
            "policies": policies or [],
        }
        return await self._request("POST", f"/accounts/{self.account_id}/access/apps", json=data)

    async def create_access_policy(
        self,
        application_id: str,
        name: str,
        decision: str = "allow",
        include: list[dict] = None,
        require: list[dict] = None,
    ) -> dict:
        """Crear política de acceso."""
        data = {
            "name": name,
            "decision": decision,
            "include": include or [],
            "require": require or [],
        }
        return await self._request(
            "POST", f"/accounts/{self.account_id}/access/apps/{application_id}/policies", json=data
        )

    async def list_access_groups(self) -> list[dict]:
        """Listar grupos de acceso."""
        result = await self._request("GET", f"/accounts/{self.account_id}/access/groups")
        return result if isinstance(result, list) else result.get("result", [])

    async def create_access_group(self, name: str, include: list[dict] = None) -> dict:
        """Crear grupo de acceso."""
        data = {"name": name, "include": include or []}
        return await self._request("POST", f"/accounts/{self.account_id}/access/groups", json=data)

    # =========================================================================
    # CLOUDFLARE TUNNELS
    # =========================================================================

    async def list_tunnels(self) -> list[dict]:
        """Listar tunnels."""
        result = await self._request("GET", f"/accounts/{self.account_id}/cfd_tunnel")
        return result if isinstance(result, list) else result.get("result", [])

    async def create_tunnel(self, name: str, config_src: str = "cloudflare") -> dict:
        """Crear tunnel."""
        data = {"name": name, "config_src": config_src}
        return await self._request("POST", f"/accounts/{self.account_id}/cfd_tunnel", json=data)

    async def update_tunnel_config(self, tunnel_id: str, config: dict) -> dict:
        """Actualizar configuración de tunnel."""
        return await self._request(
            "PUT", f"/accounts/{self.account_id}/cfd_tunnel/{tunnel_id}/configurations", json=config
        )

    async def get_tunnel_config(self, tunnel_id: str) -> dict:
        """Obtener configuración de tunnel."""
        result = await self._request("GET", f"/accounts/{self.account_id}/cfd_tunnel/{tunnel_id}/configurations")
        return result if isinstance(result, dict) else result.get("result", {})

    async def delete_tunnel(self, tunnel_id: str) -> bool:
        """Eliminar tunnel."""
        await self._request("DELETE", f"/accounts/{self.account_id}/cfd_tunnel/{tunnel_id}")
        return True

    # =========================================================================
    # WAF / FIREWALL RULES
    # =========================================================================

    async def list_firewall_rules(self, zone_id: str = None) -> list[dict]:
        """Listar reglas de firewall."""
        zone = zone_id or self.zone_id
        result = await self._request("GET", f"/zones/{zone}/firewall/rules")
        return result if isinstance(result, list) else result.get("result", [])

    async def create_firewall_rule(
        self,
        zone_id: str = None,
        filter: str = "",
        action: str = "block",
        description: str = "",
        action_parameters: dict = None,
    ) -> dict:
        """Crear regla de firewall."""
        zone = zone_id or self.zone_id
        data = {
            "filter": filter,
            "action": action,
            "description": description,
            "action_parameters": action_parameters or {},
        }
        return await self._request("POST", f"/zones/{zone}/firewall/rules", json=data)

    async def delete_firewall_rule(self, rule_id: str, zone_id: str = None) -> bool:
        """Eliminar regla de firewall."""
        zone = zone_id or self.zone_id
        await self._request("DELETE", f"/zones/{zone}/firewall/rules/{rule_id}")
        return True

    # =========================================================================
    # SSL / TLS
    # =========================================================================

    async def get_ssl_settings(self, zone_id: str = None) -> dict:
        """Obtener configuración SSL."""
        zone = zone_id or self.zone_id
        return await self._request("GET", f"/zones/{zone}/ssl/settings")

    async def update_ssl_settings(self, zone_id: str = None, **settings) -> dict:
        """Actualizar configuración SSL."""
        zone = zone_id or self.zone_id
        return await self._request("PATCH", f"/zones/{zone}/ssl/settings", json=settings)

    async def list_certificates(self, zone_id: str = None) -> list[dict]:
        """Listar certificados SSL."""
        zone = zone_id or self.zone_id
        result = await self._request("GET", f"/zones/{zone}/ssl/certificates")
        return result if isinstance(result, list) else result.get("result", [])

    async def order_certificate(self, zone_id: str = None, hosts: list[str] = None, type: str = "universal") -> dict:
        """Solicitar certificado (Let's Encrypt / Universal SSL)."""
        zone = zone_id or self.zone_id
        data = {"hosts": hosts or [], "type": type}
        return await self._request("POST", f"/zones/{zone}/ssl/certificates", json=data)

    # =========================================================================
    # CACHE / PURGE
    # =========================================================================

    async def purge_cache(
        self, zone_id: str = None, files: list[str] = None, tags: list[str] = None, purge_everything: bool = False
    ) -> dict:
        """Purgar cache."""
        zone = zone_id or self.zone_id
        data = {"purge_everything": purge_everything}
        if files:
            data["files"] = files
        if tags:
            data["tags"] = tags
        return await self._request("POST", f"/zones/{zone}/purge_cache", json=data)

    # =========================================================================
    # ANALYTICS
    # =========================================================================

    async def get_analytics(
        self, zone_id: str = None, since: str = None, until: str = None, continuous: bool = False
    ) -> dict:
        """Obtener analíticas de zona."""
        zone = zone_id or self.zone_id
        params = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if continuous:
            params["continuous"] = "true"
        return await self._request("GET", f"/zones/{zone}/analytics/dashboard", params=params)

    # =========================================================================
    # WORKERS / PAGES
    # =========================================================================

    async def list_workers(self) -> list[dict]:
        """Listar Workers."""
        result = await self._request("GET", f"/accounts/{self.account_id}/workers/scripts")
        return result if isinstance(result, list) else result.get("result", [])

    async def create_worker(self, name: str, script: str) -> dict:
        """Crear Worker."""
        data = {"name": name, "script": script}
        return await self._request("PUT", f"/accounts/{self.account_id}/workers/scripts/{name}", json=data)

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    async def create_rate_limit(
        self, zone_id: str = None, threshold: int = 100, period: int = 60, action: str = "block", description: str = ""
    ) -> dict:
        """Crear rate limiting rule."""
        zone = zone_id or self.zone_id
        data = {
            "threshold": threshold,
            "period": period,
            "action": action,
            "description": description,
        }
        return await self._request("POST", f"/zones/{zone}/rate_limits", json=data)


class CloudflareManager:
    """Gestor de alto nivel para Cloudflare."""

    def __init__(self, config: dict):
        self.adapter = CloudflareAdapter(config)

    async def setup_production_dns(self, domain: str, records: list[dict]) -> dict:
        """Configurar DNS completo para producción."""
        results = []
        for record in records:
            try:
                result = await self.adapter.create_dns_record(
                    type=record.get("type", "A"),
                    name=record.get("name", "@"),
                    content=record.get("content"),
                    proxied=record.get("proxied", True),
                    comment=f"Production setup - {record.get('name', '@')}",
                )
                results.append({"record": record, "result": result, "success": True})
            except Exception as e:
                results.append({"record": record, "error": str(e), "success": False})

        return {"success": all(r["success"] for r in results), "results": results}

    async def setup_access_for_dashboard(self, dashboard_domain: str, admin_emails: list[str]) -> dict:
        """Configurar Cloudflare Access para dashboard interno."""
        # 1. Crear aplicación Access
        app = await self.adapter.create_access_application(
            name="Transvega Dashboard",
            domain=dashboard_domain,
        )

        # 2. Crear política para emails autorizados
        include = [{"email": {"email": email}} for email in admin_emails]
        policy = await self.adapter.create_access_policy(
            application_id=app["id"],
            name="Admins Transvega",
            decision="allow",
            include=include,
        )

        # 3. Crear grupo para admins
        group = await self.adapter.create_access_group(
            name="Transvega Admins",
            include=[{"email": {"email": email}} for email in admin_emails],
        )

        return {
            "application": app,
            "policy": policy,
            "group": group,
        }

    async def setup_tunnel_for_local_services(self, tunnel_name: str, services: list[dict]) -> dict:
        """Configurar tunnel para servicios locales."""
        # 1. Crear tunnel
        tunnel = await self.adapter.create_tunnel(tunnel_name)

        # 2. Configurar ingress rules
        config = {
            "config": {
                "ingress": [
                    {
                        "hostname": svc["hostname"],
                        "service": f"http://{svc['internal_host']}:{svc['port']}",
                        "originRequest": {"connectTimeout": "30s", "noTLSVerify": True},
                    }
                    for svc in services
                ]
                + [{"service": "http_status:404"}]  # Catch-all
            }
        }
        await self.adapter.update_tunnel_config(tunnel["id"], config)

        return {
            "tunnel": tunnel,
            "config": config,
            "token": tunnel.get("tunnel_secret"),  # Para cloudflared
        }

    async def configure_waf_rules(self, rules: list[dict]) -> dict:
        """Configurar reglas WAF."""
        results = []
        for rule in rules:
            try:
                result = await self.adapter.create_firewall_rule(
                    filter=rule["filter"],
                    action=rule.get("action", "block"),
                    description=rule.get("description", ""),
                    action_parameters=rule.get("action_parameters"),
                )
                results.append({"rule": rule, "result": result, "success": True})
            except Exception as e:
                results.append({"rule": rule, "error": str(e), "success": False})

        return {"success": all(r["success"] for r in results), "results": results}

    async def configure_ssl(self, zone_id: str = None, settings: dict = None) -> dict:
        """Configurar SSL/TLS."""
        defaults = {
            "min_tls_version": "1.2",
            "always_use_https": "on",
            "automatic_https_rewrites": "on",
            "ssl": "full",
        }
        settings = {**defaults, **(settings or {})}
        return await self.adapter.update_ssl_settings(zone_id, **settings)

    async def order_ssl_certificate(self, hosts: list[str]) -> dict:
        """Solicitar certificado SSL."""
        return await self.adapter.order_certificate(hosts=hosts)

    async def purge_all_cache(self) -> dict:
        """Purgar todo el cache."""
        return await self.adapter.purge_cache(purge_everything=True)

    async def get_zone_analytics(self, since: str = None, until: str = None) -> dict:
        """Obtener analíticas de zona."""
        return await self.adapter.get_analytics(since=since, until=until)

    async def deploy_worker(self, name: str, script: str) -> dict:
        """Desplegar Cloudflare Worker."""
        return await self.adapter.create_worker(name, script)
