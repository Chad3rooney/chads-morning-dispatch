"""Tiny resilient HTTP layer built on urllib — no third-party packages.

Every external data source (Yahoo Finance, RSS feeds, the Anthropic API) goes
through here so retries, timeouts, a browser User-Agent and a shared cookie jar
are applied consistently. Two things matter for Yahoo: a browser User-Agent and
a session cookie — without the cookie Yahoo's finance endpoints return HTTP 429.
"""

import gzip
import http.cookiejar          # stdlib (absolute import; not the sibling module)
import json
import os
import shutil
import ssl
import subprocess
import tempfile
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

# A shared cookie jar + opener so a session cookie is captured once and resent
# on every subsequent request. Yahoo Finance, in particular, returns HTTP 429
# to cookieless clients; seeding a consent cookie (see markets._prime_session)
# unblocks it. Cookie processing runs before the error handler, so cookies are
# captured even from a non-2xx seed response.
_COOKIE_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_SSL_CONTEXT),
    urllib.request.HTTPCookieProcessor(_COOKIE_JAR),
)


def cookie_count():
    """Number of cookies currently held — lets callers confirm a primed session."""
    return len(_COOKIE_JAR)


# A second transport: the system `curl`. Some hosts (notably Yahoo Finance via
# Akamai) fingerprint the TLS handshake and reject Python's urllib — especially
# on older OpenSSL builds — while accepting curl. curl ships on macOS and on
# GitHub's Ubuntu runners, so this keeps us reliable in both places without any
# pip install. It shares its own cookie jar file so a primed session persists
# across calls. Entirely optional: if curl is absent we simply fall back to
# urllib and the briefing degrades gracefully, exactly as before.
_CURL = shutil.which("curl")
_CURL_JAR = os.path.join(tempfile.gettempdir(), "dispatch-curl-cookies.txt")


def _curl_get(url, timeout):
    """GET via the system curl, sharing a persistent cookie jar. None on any
    failure or if curl isn't installed."""
    if not _CURL:
        return None
    try:
        proc = subprocess.run(
            [_CURL, "-sL", "--compressed",
             "--max-time", str(int(timeout)),
             "-A", USER_AGENT,
             "-H", "Accept-Language: en-AU,en;q=0.9",
             "-b", _CURL_JAR, "-c", _CURL_JAR, url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout + 5,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _open(req, timeout):
    resp = _OPENER.open(req, timeout=timeout)
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def get(url, timeout=DEFAULT_TIMEOUT, retries=3, headers=None, prefer_curl=False):
    """GET a URL as text, with retries + exponential backoff.

    Returns the body string, or None if every attempt failed. Never raises —
    a failed source must degrade the briefing gracefully, not break it.

    prefer_curl=True routes straight through the system curl when available
    (used for Yahoo, which fingerprint-blocks Python's TLS). Either way, curl is
    tried as a last-ditch fallback if the urllib path fails and curl is present.
    """
    if prefer_curl and _CURL:
        return _curl_get(url, timeout)

    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip",
    }
    if headers:
        hdrs.update(headers)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            return _open(req, timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            code = getattr(e, "code", None)
            # Don't waste retries on a hard 404/410.
            if code in (404, 410):
                break
            time.sleep(0.6 * (2 ** attempt))
    # urllib exhausted — try curl once before giving up.
    return _curl_get(url, timeout)


def get_json(url, timeout=DEFAULT_TIMEOUT, retries=3, headers=None, prefer_curl=False):
    """GET and parse JSON, or None on any failure."""
    body = get(url, timeout=timeout, retries=retries, headers=headers, prefer_curl=prefer_curl)
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
