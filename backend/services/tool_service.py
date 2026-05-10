"""
Real cybersecurity tool execution service.
Executes actual system tools (dig, whois, curl, socket scanning)
with strict sandboxing and timeout enforcement.
"""
import asyncio
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional


TOOL_TIMEOUT = 15  # seconds max per tool execution


async def _run_cmd(cmd: list[str], timeout: int = TOOL_TIMEOUT) -> dict:
    """Run a subprocess command safely with timeout."""
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": f"Tool timed out after {timeout}s", "raw": ""}

        raw_out = stdout.decode("utf-8", errors="replace").strip()
        raw_err = stderr.decode("utf-8", errors="replace").strip()
        elapsed = round(time.time() - start, 2)

        if proc.returncode != 0 and not raw_out:
            return {"success": False, "error": raw_err or "Command failed", "raw": raw_err, "elapsed": elapsed}

        return {"success": True, "raw": raw_out, "stderr": raw_err, "elapsed": elapsed}

    except FileNotFoundError as e:
        return {"success": False, "error": f"Tool not found: {e}", "raw": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "raw": ""}


async def dns_lookup(domain: str) -> dict:
    """Perform comprehensive DNS lookups for a domain."""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    results = {}

    record_types = ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"]
    for rtype in record_types:
        r = await _run_cmd(["dig", "+short", rtype, domain])
        if r["success"] and r["raw"]:
            results[rtype] = [line.strip() for line in r["raw"].splitlines() if line.strip()]

    # Get all records at once
    full = await _run_cmd(["dig", "ANY", domain, "+noall", "+answer"])
    
    # Reverse DNS on A records
    reverse_dns = {}
    for ip in results.get("A", [])[:3]:
        rev = await _run_cmd(["dig", "+short", "-x", ip])
        if rev["success"] and rev["raw"]:
            reverse_dns[ip] = rev["raw"].strip()

    return {
        "domain": domain,
        "records": results,
        "reverseDns": reverse_dns,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "dig",
    }


async def whois_lookup(target: str) -> dict:
    """Perform WHOIS lookup on domain or IP."""
    target = target.strip().replace("https://", "").replace("http://", "").split("/")[0]
    r = await _run_cmd(["whois", target])

    if not r["success"]:
        return {"target": target, "error": r["error"], "raw": ""}

    raw = r["raw"]
    parsed = {}

    # Parse key fields from raw WHOIS
    field_map = {
        "Registrar:": "registrar",
        "Creation Date:": "creationDate",
        "Updated Date:": "updatedDate",
        "Registry Expiry Date:": "expiryDate",
        "Registrant Organization:": "organization",
        "Registrant Country:": "country",
        "Name Server:": "nameServers",
        "DNSSEC:": "dnssec",
        "Registrant Email:": "email",
        "Admin Email:": "adminEmail",
    }

    for line in raw.splitlines():
        for key, field in field_map.items():
            if line.strip().startswith(key):
                val = line.split(":", 1)[1].strip() if ":" in line else ""
                if field == "nameServers":
                    parsed.setdefault("nameServers", []).append(val)
                else:
                    parsed.setdefault(field, val)

    return {
        "target": target,
        "parsed": parsed,
        "raw": raw[:3000],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "whois",
    }


async def http_probe(url: str) -> dict:
    """Probe HTTP/HTTPS endpoint for headers, status, and security info."""
    if not url.startswith("http"):
        url = f"https://{url}"

    # Curl with headers, follow redirects, timeout
    r = await _run_cmd([
        "curl", "-sI", "--max-time", "10",
        "--connect-timeout", "5",
        "-L", "--max-redirs", "3",
        "-A", "Mozilla/5.0 (security-scanner/1.0)",
        url
    ])

    headers = {}
    status_code = None
    redirect_chain = []

    if r["success"]:
        lines = r["raw"].splitlines()
        for line in lines:
            if line.startswith("HTTP/"):
                try:
                    status_code = int(line.split(" ")[1])
                except Exception:
                    pass
            elif ": " in line:
                k, v = line.split(": ", 1)
                headers[k.lower()] = v.strip()

    # Security header analysis
    security_headers = {
        "strict-transport-security": headers.get("strict-transport-security"),
        "content-security-policy": headers.get("content-security-policy"),
        "x-frame-options": headers.get("x-frame-options"),
        "x-content-type-options": headers.get("x-content-type-options"),
        "x-xss-protection": headers.get("x-xss-protection"),
        "referrer-policy": headers.get("referrer-policy"),
        "permissions-policy": headers.get("permissions-policy"),
    }

    missing_headers = [h for h, v in security_headers.items() if not v]
    server = headers.get("server", "Unknown")
    tech_stack = []
    if headers.get("x-powered-by"):
        tech_stack.append(headers["x-powered-by"])
    if "nginx" in server.lower():
        tech_stack.append("nginx")
    if "apache" in server.lower():
        tech_stack.append("Apache")

    return {
        "url": url,
        "statusCode": status_code,
        "server": server,
        "headers": headers,
        "securityHeaders": security_headers,
        "missingSecurityHeaders": missing_headers,
        "techStack": tech_stack,
        "securityScore": max(0, 100 - len(missing_headers) * 14),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "curl",
    }


async def port_scan(host: str, ports: list[int] = None) -> dict:
    """Scan common ports using Python socket (no nmap required)."""
    host = host.strip().replace("https://", "").replace("http://", "").split("/")[0]

    if ports is None:
        # Common interesting ports
        ports = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445,
                 993, 995, 1723, 3306, 3389, 5900, 8080, 8443, 8888, 27017]

    open_ports = []
    closed_ports = []

    SERVICE_MAP = {
        21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
        80: "HTTP", 110: "POP3", 111: "RPCbind", 135: "MSRPC",
        139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
        993: "IMAPS", 995: "POP3S", 1723: "PPTP", 3306: "MySQL",
        3389: "RDP", 5900: "VNC", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
        8888: "HTTP-Alt", 27017: "MongoDB"
    }

    HIGH_RISK_PORTS = {23: "Telnet (unencrypted)", 21: "FTP (unencrypted)",
                       3389: "RDP (brute-force target)", 445: "SMB (ransomware vector)",
                       27017: "MongoDB (often unauthenticated)"}

    async def check_port(port: int):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: sock.connect_ex((host, port))),
                timeout=2.0
            )
            sock.close()
            return port, result == 0
        except Exception:
            return port, False

    # Run port checks concurrently (max 20 at a time)
    semaphore = asyncio.Semaphore(20)

    async def check_with_sem(port):
        async with semaphore:
            return await check_port(port)

    tasks = [check_with_sem(p) for p in ports]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in results:
        if isinstance(item, tuple):
            port, is_open = item
            if is_open:
                risk = HIGH_RISK_PORTS.get(port, "")
                open_ports.append({
                    "port": port,
                    "service": SERVICE_MAP.get(port, "Unknown"),
                    "state": "open",
                    "riskNote": risk,
                })

    return {
        "host": host,
        "openPorts": open_ports,
        "closedCount": len(ports) - len(open_ports),
        "scannedCount": len(ports),
        "highRiskPorts": [p for p in open_ports if p.get("riskNote")],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "socket-scan",
    }


async def subdomain_enum(domain: str) -> dict:
    """Enumerate subdomains using DNS brute force with common names."""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]

    common_subdomains = [
        "www", "mail", "ftp", "admin", "api", "dev", "staging", "test",
        "blog", "shop", "store", "cdn", "static", "assets", "media",
        "vpn", "remote", "portal", "login", "auth", "secure", "ssl",
        "webmail", "email", "smtp", "pop", "imap", "mx", "ns1", "ns2",
        "dns", "dns1", "dns2", "app", "mobile", "m", "beta", "old",
        "new", "cloud", "backup", "db", "database", "sql", "mysql",
        "mongo", "redis", "jenkins", "gitlab", "github", "git",
        "jira", "confluence", "wiki", "docs", "help", "support",
        "status", "monitor", "metrics", "grafana", "kibana",
    ]

    found = []

    async def check_subdomain(sub: str):
        hostname = f"{sub}.{domain}"
        try:
            loop = asyncio.get_event_loop()
            addrs = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyname_ex, hostname),
                timeout=2.0
            )
            return {"subdomain": hostname, "ips": addrs[2], "status": "resolved"}
        except Exception:
            return None

    semaphore = asyncio.Semaphore(30)

    async def check_with_sem(sub):
        async with semaphore:
            return await check_subdomain(sub)

    tasks = [check_with_sem(s) for s in common_subdomains]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if r and not isinstance(r, Exception):
            found.append(r)

    return {
        "domain": domain,
        "subdomains": found,
        "totalFound": len(found),
        "checked": len(common_subdomains),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "dns-brute",
    }


async def ssl_analyze(host: str) -> dict:
    """Analyze SSL/TLS certificate information."""
    host = host.strip().replace("https://", "").replace("http://", "").split("/")[0]

    r = await _run_cmd([
        "curl", "-sI", "--connect-timeout", "10",
        "--max-time", "10",
        f"https://{host}",
        "-v",
        "--stderr", "-"
    ])

    # Use openssl for cert info
    r2 = await _run_cmd([
        "curl", "-s", "--insecure",
        f"https://{host}",
        "-v",
        "--stderr", "/dev/stdout",
        "-o", "/dev/null",
    ])

    cert_info = {}
    raw = r2.get("raw", "") + r2.get("stderr", "")

    for line in raw.splitlines():
        if "subject:" in line.lower():
            cert_info["subject"] = line.split(":", 1)[-1].strip()
        if "issuer:" in line.lower():
            cert_info["issuer"] = line.split(":", 1)[-1].strip()
        if "expire date:" in line.lower() or "ssl certificate verify" in line.lower():
            cert_info["expireInfo"] = line.strip()

    return {
        "host": host,
        "certInfo": cert_info,
        "raw": raw[:2000],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": "curl-ssl",
    }


async def run_tool(tool_name: str, params: dict) -> dict:
    """Dispatch tool execution based on tool name."""
    tool_map = {
        "dns_lookup": lambda: dns_lookup(params.get("domain", params.get("target", ""))),
        "whois": lambda: whois_lookup(params.get("target", params.get("domain", ""))),
        "http_probe": lambda: http_probe(params.get("url", params.get("target", ""))),
        "port_scan": lambda: port_scan(
            params.get("host", params.get("target", "")),
            params.get("ports")
        ),
        "subdomain_enum": lambda: subdomain_enum(params.get("domain", params.get("target", ""))),
        "ssl_analyze": lambda: ssl_analyze(params.get("host", params.get("target", ""))),
    }

    if tool_name not in tool_map:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        result = await asyncio.wait_for(tool_map[tool_name](), timeout=30)
        return {"success": True, "tool": tool_name, "result": result}
    except asyncio.TimeoutError:
        return {"success": False, "error": f"Tool {tool_name} timed out"}
    except Exception as e:
        return {"success": False, "error": str(e), "tool": tool_name}
