"""Universal BYOK relay proxy (OpenAI, Ollama, custom)."""
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 6

# Hostnames that always resolve to cloud metadata services.
_CLOUD_METADATA_HOSTS = {
    "169.254.169.254",
    "100.100.100.200",
    "fd00:ec2::254",
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "instance-data",
}

# Cloud metadata IPs that are ALWAYS rejected, even with the opt-in.
_ALWAYS_BLOCKED_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
})


def _allow_private_endpoints():
    """Return True only when the operator explicitly opted in."""
    return os.environ.get("QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS", "0") == "1"


def _classifier_allowed_hosts():
    """Return the optional allowlist of endpoint hostnames (lowercase)."""
    raw = os.environ.get("QUICK_PICK_CLASSIFIER_ALLOWED_HOSTS", "")
    return {h.strip().lower().rstrip(".") for h in raw.split(",") if h.strip().rstrip(".")}


def _candidate_ips(ip):
    """Return [ip] plus the unwrapped IPv4 for IPv4-mapped IPv6 addresses."""
    out = [ip]
    try:
        mapped = ip.ipv4_mapped
    except AttributeError:
        mapped = None
    if mapped is not None:
        out.append(mapped)
    return out


def _ip_blocked_always(ip):
    """Check addresses that are never valid classifier targets."""
    for cand in _candidate_ips(ip):
        if cand in _ALWAYS_BLOCKED_IPS:
            return True
        if cand.is_unspecified or cand.is_multicast or cand.is_reserved or cand.is_link_local:
            return True
    return False


def _ip_blocked_when_private_closed(ip):
    """Check addresses blocked unless the private-endpoint opt-in is set."""
    for cand in _candidate_ips(ip):
        if cand.is_loopback or cand.is_private or cand.is_link_local:
            return True
        if not cand.is_global:
            # Covers CGNAT 100.64.0.0/10, unspecified, multicast, reserved.
            return True
    return False


def _validate_target(url):
    """Resolve ONCE and validate. Return (parsed, hostname, port, pinned_ips).

    Raises ValueError when the endpoint is not allowed.
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("URL invalide (doit débuter par http:// ou https://)")
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Nom d'hôte manquant dans l'URL")
    # Normalize case and the trailing root dot ("metadata.goog." == "metadata.goog").
    host_norm = hostname.lower().rstrip(".")
    allowed = _classifier_allowed_hosts()
    if allowed and host_norm not in allowed:
        raise ValueError("Hôte de l'endpoint absent de la liste autorisée")
    if host_norm in _CLOUD_METADATA_HOSTS:
        raise ValueError("Accès interdit aux services de métadonnées cloud")
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Impossible de résoudre le nom d'hôte : {hostname}")
    ips = [ai[4][0] for ai in addr_info]
    if not ips:
        raise ValueError(f"Impossible de résoudre le nom d'hôte : {hostname}")
    allow_private = _allow_private_endpoints()
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Impossible de résoudre le nom d'hôte : {hostname}")
        # A single bad address rejects the whole endpoint (DNS rebinding).
        if _ip_blocked_always(ip):
            raise ValueError("L'endpoint résout vers une adresse interdite")
        if not allow_private and _ip_blocked_when_private_closed(ip):
            raise ValueError("Accès aux adresses privées et locales désactivé")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    # Deduplicated validated IPs, order preserved; callers try each in turn.
    pinned_ips = list(dict.fromkeys(ips))
    return parsed, hostname, port, pinned_ips


def is_safe_url(url: str) -> tuple[bool, str]:
    """Check that an endpoint URL is allowed (single DNS resolution)."""
    try:
        _validate_target(url)
    except ValueError as err:
        return False, str(err)
    return True, ""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that never follows redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirection bloquée (non suivie)", headers, fp)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection pinned to pre-validated IPs (no second DNS lookup)."""

    def __init__(self, host, port=None, pinned_ip=None, pinned_ips=None, **kwargs):
        super().__init__(host, port, **kwargs)
        if pinned_ips is not None:
            self._pinned_ips = list(pinned_ips)
        elif pinned_ip is not None:
            self._pinned_ips = [pinned_ip]
        else:
            self._pinned_ips = [host]

    def connect(self):
        last_err = None
        for ip in self._pinned_ips:
            try:
                self.sock = socket.create_connection(
                    (ip, self.port), self.timeout, self.source_address)
                return
            except OSError as err:
                last_err = err
        raise last_err


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to pre-validated IPs, SNI kept on hostname."""

    def __init__(self, host, port=None, pinned_ip=None, pinned_ips=None, **kwargs):
        super().__init__(host, port, **kwargs)
        if pinned_ips is not None:
            self._pinned_ips = list(pinned_ips)
        elif pinned_ip is not None:
            self._pinned_ips = [pinned_ip]
        else:
            self._pinned_ips = [host]

    def connect(self):
        last_err = None
        for ip in self._pinned_ips:
            try:
                sock = socket.create_connection(
                    (ip, self.port), self.timeout, self.source_address)
            except OSError as err:
                last_err = err
                continue
            context = self._context or ssl.create_default_context()
            self.sock = context.wrap_socket(sock, server_hostname=self.host)
            return
        raise last_err


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    """urllib handler routing HTTP through the validated IPs."""

    def __init__(self, pinned_ips, **kwargs):
        super().__init__(**kwargs)
        self._pinned_ips = [pinned_ips] if isinstance(pinned_ips, str) else list(pinned_ips)

    def http_open(self, req):
        pinned_ips = self._pinned_ips

        class _Bound(_PinnedHTTPConnection):
            def __init__(self, host, port=None, **kw):
                super().__init__(host, port, pinned_ips=pinned_ips, **kw)

        return self.do_open(_Bound, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib handler routing HTTPS through the validated IPs."""

    def __init__(self, pinned_ips, **kwargs):
        super().__init__(**kwargs)
        self._pinned_ips = [pinned_ips] if isinstance(pinned_ips, str) else list(pinned_ips)

    def https_open(self, req):
        pinned_ips = self._pinned_ips

        class _Bound(_PinnedHTTPSConnection):
            def __init__(self, host, port=None, **kw):
                super().__init__(host, port, pinned_ips=pinned_ips, **kw)

        return self.do_open(_Bound, req)


def _send_request(method, url, headers=None, data=None, timeout=DEFAULT_TIMEOUT):
    """Send ONE outbound request: single DNS resolution, no proxy, no redirect.

    Returns (status, response_headers, body_bytes). A 3xx response raises
    urllib.error.HTTPError (never followed).
    """
    _parsed, _hostname, _port, pinned_ips = _validate_target(url)
    opener = urllib.request.build_opener(
        _PinnedHTTPHandler(pinned_ips),
        _PinnedHTTPSHandler(pinned_ips),
        _NoRedirectHandler(),
        urllib.request.ProxyHandler({}),
    )
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, dict(resp.headers or {}), resp.read()


def _auth_header(api_key):
    if not api_key:
        return None
    clean_key = str(api_key).strip()
    if not clean_key:
        return None
    if clean_key.lower().startswith("bearer "):
        return clean_key
    return f"Bearer {clean_key}"


def query_external_classifier(endpoint, api_key, payload_dict, timeout=DEFAULT_TIMEOUT):
    """Send a classification request to a remote HTTP/HTTPS endpoint."""
    mode = payload_dict.get("provider") or payload_dict.get("mode")
    model = payload_dict.get("model") or "gpt-4o-mini"
    is_openai_mode = (mode == "openai") or ("/chat/completions" in endpoint)

    target_url = endpoint
    if is_openai_mode and not target_url.endswith("/chat/completions"):
        target_url = target_url.rstrip("/") + "/chat/completions"

    if is_openai_mode:
        candidate_actions = payload_dict.get("candidate_actions") or []
        user_content = json.dumps({
            "title": payload_dict.get("title", ""),
            "description": payload_dict.get("description", ""),
            "bullets": payload_dict.get("bullets", []),
            "candidate_actions": candidate_actions,
        }, ensure_ascii=False)
        system_prompt = (
            "You are a card decision classifier. Analyze the item and pick the single best action "
            f"from candidate_actions: {candidate_actions}. "
            "Return strictly a JSON object: {\"action\": \"<action_id>\", \"confidence\": 0.9, \"reasoning\": \"brief reason\"}"
        )
        post_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }
    else:
        post_data = payload_dict

    data_bytes = json.dumps(post_data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    auth = _auth_header(api_key)
    if auth:
        headers["Authorization"] = auth

    try:
        status, _resp_headers, raw = _send_request(
            "POST", target_url, headers, data_bytes, timeout)
        raw_body = raw.decode("utf-8")
        try:
            res_json = json.loads(raw_body)
        except json.JSONDecodeError:
            res_json = {"raw": raw_body}

        if is_openai_mode and isinstance(res_json, dict) and "choices" in res_json:
            try:
                content_text = res_json["choices"][0]["message"]["content"]
                match = re.search(r"\{.*\}", content_text, re.DOTALL)
                if match:
                    parsed_pred = json.loads(match.group(0))
                    return status, parsed_pred
            except Exception:
                pass
        return status, res_json
    except urllib.error.HTTPError as err:
        try:
            err_body = err.read().decode("utf-8", errors="ignore")
        except Exception:
            err_body = ""
        finally:
            try:
                err.close()
            except Exception:
                pass
        return err.code, {"error": f"HTTP {err.code}: {err.reason}", "detail": err_body}
    except ValueError:
        raise
    except Exception as err:
        return 500, {"error": str(err)}


def test_external_classifier(endpoint, api_key, timeout=DEFAULT_TIMEOUT):
    """Probe that a classifier endpoint is reachable."""
    parsed = urlparse(endpoint)
    auth = _auth_header(api_key)
    headers = dict([("Authorization", auth)] if auth else [])

    if parsed.path.rstrip("/").endswith("/v1"):
        models_url = endpoint.rstrip("/") + "/models"
        try:
            status, _h, _b = _send_request("GET", models_url, headers, None, timeout)
            return status, True, f"API OpenAI/Ollama joignable (HTTP {status})"
        except Exception:
            pass  # Fall back to the generic POST ping below.

    ping_payload = {"ping": True, "title": "test", "candidate_actions": ["approve", "reject"]}
    data = json.dumps(ping_payload).encode("utf-8")
    post_headers = {"Content-Type": "application/json"}
    post_headers.update(headers)

    try:
        status, _h, _b = _send_request("POST", endpoint, post_headers, data, timeout)
        return status, True, f"Connexion réussie (HTTP {status})"
    except urllib.error.HTTPError as err:
        try:
            err.close()
        except Exception:
            pass
        if err.code in (200, 204, 400, 422):
            return err.code, True, f"Endpoint joignable (HTTP {err.code})"
        if err.code in (404, 405):
            try:
                get_status, _h, _b = _send_request("GET", endpoint, headers, None, timeout)
                return get_status, True, f"Endpoint joignable (HTTP {get_status})"
            except urllib.error.HTTPError as get_err:
                try:
                    get_err.close()
                except Exception:
                    pass
                if get_err.code in (200, 204, 400, 401, 403, 422):
                    return get_err.code, True, f"Endpoint joignable (HTTP {get_err.code})"
        return err.code, False, f"Erreur d'authentification ou endpoint (HTTP {err.code}: {err.reason})"
    except ValueError:
        raise
    except Exception as err:
        return 500, False, f"Hôte injoignable : {err}"
