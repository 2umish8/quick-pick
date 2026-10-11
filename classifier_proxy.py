"""Module de relai (proxy) et adaptateur universel BYOK (OpenAI, Ollama, custom)."""
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 6


def is_safe_url(url: str) -> tuple[bool, str]:
    """Protège contre les attaques SSRF et l'exfiltration de métadonnées cloud."""
    if not url or not url.startswith(("http://", "https://")):
        return False, "URL invalide (doit débuter par http:// ou https://)"
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False, "Nom d'hôte manquant dans l'URL"

    # Toujours bloquer les métadonnées cloud critiques
    blocked_hosts = {"169.254.169.254", "metadata.google.internal", "instance-data"}
    if hostname.lower() in blocked_hosts:
        return False, "Accès interdit aux services de métadonnées cloud"

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        ips = [ai[4][0] for ai in addr_info]
    except socket.gaierror:
        return False, f"Impossible de résoudre le nom d'hôte : {hostname}"

    allow_private = os.environ.get("QUICK_PICK_ALLOW_PRIVATE_ENDPOINTS", "1") == "1"
    for ip_str in ips:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_link_local:
            return False, "Accès interdit aux adresses link-local"
        if not allow_private and (ip.is_loopback or ip.is_private):
            return False, "Accès aux adresses privées et locales désactivé"
    return True, ""


def query_external_classifier(endpoint, api_key, payload_dict, timeout=DEFAULT_TIMEOUT):
    """Envoie une requête de classification à un endpoint HTTP/HTTPS distant (format standard ou OpenAI)."""
    ok, err_msg = is_safe_url(endpoint)
    if not ok:
        raise ValueError(err_msg)

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
    req = urllib.request.Request(target_url, data=data_bytes, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        clean_key = str(api_key).strip()
        auth_header = clean_key if clean_key.lower().startswith("bearer ") else f"Bearer {clean_key}"
        req.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
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
                        return resp.status, parsed_pred
                except Exception:
                    pass
            return resp.status, res_json
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="ignore")
        return err.code, {"error": f"HTTP {err.code}: {err.reason}", "detail": err_body}
    except Exception as err:
        return 500, {"error": str(err)}


def test_external_classifier(endpoint, api_key, timeout=DEFAULT_TIMEOUT):
    """Teste la joignabilité d'un endpoint de classifieur."""
    ok, err_msg = is_safe_url(endpoint)
    if not ok:
        raise ValueError(err_msg)

    # Si c'est un endpoint de type OpenAI base (ex: https://api.openai.com/v1 ou http://localhost:11434/v1)
    # on teste /models en GET d'abord si pas de chemin spécifique
    parsed = urlparse(endpoint)
    auth_header = None
    if api_key:
        clean_key = str(api_key).strip()
        auth_header = clean_key if clean_key.lower().startswith("bearer ") else f"Bearer {clean_key}"

    if parsed.path.rstrip("/").endswith("/v1"):
        models_url = endpoint.rstrip("/") + "/models"
        try:
            req = urllib.request.Request(models_url, method="GET")
            if auth_header:
                req.add_header("Authorization", auth_header)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, True, f"API OpenAI/Ollama joignable (HTTP {resp.status})"
        except Exception:
            pass  # Fallback au ping POST générique

    ping_payload = {"ping": True, "title": "test", "candidate_actions": ["approve", "reject"]}
    data = json.dumps(ping_payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, True, f"Connexion réussie (HTTP {resp.status})"
    except urllib.error.HTTPError as err:
        if err.code in (200, 204, 400, 422):
            return err.code, True, f"Endpoint joignable (HTTP {err.code})"
        if err.code in (404, 405):
            try:
                get_req = urllib.request.Request(endpoint, method="GET")
                if auth_header:
                    get_req.add_header("Authorization", auth_header)
                with urllib.request.urlopen(get_req, timeout=timeout) as get_resp:
                    return get_resp.status, True, f"Endpoint joignable (HTTP {get_resp.status})"
            except urllib.error.HTTPError as get_err:
                if get_err.code in (200, 204, 400, 401, 403, 422):
                    return get_err.code, True, f"Endpoint joignable (HTTP {get_err.code})"
        return err.code, False, f"Erreur d'authentification ou endpoint (HTTP {err.code}: {err.reason})"
    except Exception as err:
        return 500, False, f"Hôte injoignable : {err}"
