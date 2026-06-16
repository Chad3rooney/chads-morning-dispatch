"""Tiny resilient HTTP layer built on urllib — no third-party packages.

Every external data source (Yahoo Finance, RSS feeds, the Anthropic API) goes
through here so retries, timeouts and a browser User-Agent are applied
consistently. The User-Agent matters: Yahoo returns HTTP 429 without one.
"""

import gzip
import json
import os
import ssl
import time
import urllib.request
import urllib.error

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 12


def _macos_keychain_bundle():
    """Export trusted roots from the macOS keychain to a temp PEM, or None.

    Python on macOS does NOT consult the keychain, so urllib rejects certs that
    Safari/curl accept — including the roots that corporate/school networks
    (e.g. an SSL-inspecting firewall) install for their TLS interception. We
    export the same roots the system trusts so verification matches curl while
    staying fully on. No-op (returns None) off macOS, so CI is unaffected.
    """
    import platform
    import subprocess
    import tempfile
    if platform.system() != "Darwin":
        return None
    keychains = [
        "/System/Library/Keychains/SystemRootCertificates.keychain",
        "/Library/Keychains/System.keychain",
    ]
    login = os.path.expanduser("~/Library/Keychains/login.keychain-db")
    if os.path.exists(login):
        keychains.append(login)
    chunks = []
    for kc in keychains:
        try:
            out = subprocess.run(
                ["/usr/bin/security", "find-certificate", "-a", "-p", kc],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
            )
            if out.stdout:
                chunks.append(out.stdout.decode("utf-8", "replace"))
        except Exception:
            pass
    if not chunks:
        return None
    path = os.path.join(tempfile.gettempdir(), "dispatch-macos-ca.pem")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(chunks))
        return path
    except Exception:
        return None


def _make_ssl_context():
    """A verifying SSL context that also works on macOS and behind SSL-inspecting
    networks. We explicitly load the right CA bundle rather than relying on env
    propagation (which is unreliable on older Pythons). Verification stays on.
    """
    ctx = ssl.create_default_context()
    bundles = []
    env = os.environ.get("SSL_CERT_FILE")
    if env and os.path.exists(env):
        bundles.append(env)                       # explicit user override wins
    else:
        kc = _macos_keychain_bundle()             # None off macOS
        if kc:
            bundles.append(kc)
        for path in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
            if os.path.exists(path):
                bundles.append(path)
                break
    for path in bundles:
        try:
            ctx.load_verify_locations(path)
        except Exception:
            pass
    return ctx


_SSL_CONTEXT = _make_ssl_context()


def _open(req, timeout):
    resp = urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT)
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def get(url, timeout=DEFAULT_TIMEOUT, retries=3, headers=None):
    """GET a URL as text, with retries + exponential backoff.

    Returns the body string, or None if every attempt failed. Never raises —
    a failed source must degrade the briefing gracefully, not break it.
    """
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip",
    }
    if headers:
        hdrs.update(headers)

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            return _open(req, timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            last_err = e
            code = getattr(e, "code", None)
            # Don't waste retries on a hard 404/410.
            if code in (404, 410):
                break
            time.sleep(0.6 * (2 ** attempt))
    return None


def get_json(url, timeout=DEFAULT_TIMEOUT, retries=3, headers=None):
    """GET and parse JSON, or None on any failure."""
    body = get(url, timeout=timeout, retries=retries, headers=headers)
    if not body:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def post_json(url, payload, headers=None, timeout=60, retries=2):
    """POST a JSON body and parse a JSON response. Returns (data, error_str)."""
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            body = _open(req, timeout)
            return json.loads(body), None
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            last_err = "HTTP %s %s" % (e.code, detail)
            if e.code in (400, 401, 403):     # not worth retrying
                break
            time.sleep(1.0 * (2 ** attempt))
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_err = str(e)
            time.sleep(1.0 * (2 ** attempt))
    return None, last_err
