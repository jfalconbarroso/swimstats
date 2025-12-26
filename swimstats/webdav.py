import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
from urllib.parse import quote, unquote

import requests

from .config import BASE, NS, PROPFIND_BODY, SHARE_TOKEN, SHARE_PASSWORD, USE_PUBLIC_SHARE_WEBDAV


@dataclass
class DavEntry:
    href: str
    path: str
    is_dir: bool
    content_type: Optional[str]
    size: Optional[int]
    last_modified: Optional[str]
    etag: Optional[str]


def _auth() -> Optional[Tuple[str, str]]:
    # Public share WebDAV typically requires Basic Auth: username=token, password=share password.
    # Public files WebDAV often does not require auth, but providing it usually does not hurt.
    if USE_PUBLIC_SHARE_WEBDAV:
        return (SHARE_TOKEN, SHARE_PASSWORD or "")
    return None


def safe_join(base: str, path: str) -> str:
    path = path.strip("/")
    if not path:
        return base.rstrip("/") + "/"
    return base.rstrip("/") + "/" + "/".join(quote(unquote(seg)) for seg in path.split("/"))


def _href_to_rel(href: str) -> str:
    """Convert PROPFIND href to a relative path for subsequent requests.

    Supports both:
      - /remote.php/dav/public-files/<token>/...
      - /public.php/webdav/...
    """
    href_u = unquote(href)

    m1 = f"/public-files/{SHARE_TOKEN}/"
    if m1 in href_u:
        rel = href_u.split(m1, 1)[1]
        return rel.rstrip("/")

    m2 = "/public.php/webdav/"
    if m2 in href_u:
        rel = href_u.split(m2, 1)[1]
        return rel.rstrip("/")

    return href_u.lstrip("/").rstrip("/")


def propfind(url: str, depth: str = "1", timeout: int = 60) -> List[DavEntry]:
    r = requests.request(
        "PROPFIND",
        url,
        data=PROPFIND_BODY,
        headers={"Depth": depth, "Content-Type": "text/xml"},
        auth=_auth(),
        timeout=timeout,
    )
    r.raise_for_status()

    root = ET.fromstring(r.content)
    out: List[DavEntry] = []

    for resp in root.findall("d:response", NS):
        href = resp.findtext("d:href", default="", namespaces=NS)

        prop = None
        for ps in resp.findall("d:propstat", NS):
            status = ps.findtext("d:status", default="", namespaces=NS)
            if "200" in status:
                prop = ps.find("d:prop", NS)
                break
        if prop is None:
            continue

        rtype = prop.find("d:resourcetype", NS)
        is_dir = rtype is not None and rtype.find("d:collection", NS) is not None

        ctype = prop.findtext("d:getcontenttype", default=None, namespaces=NS)
        clen = prop.findtext("d:getcontentlength", default=None, namespaces=NS)
        lmod = prop.findtext("d:getlastmodified", default=None, namespaces=NS)
        etag = prop.findtext("d:getetag", default=None, namespaces=NS)

        size = int(clen) if (clen and str(clen).isdigit()) else None
        rel = _href_to_rel(href)

        out.append(
            DavEntry(
                href=href,
                path=rel,
                is_dir=is_dir,
                content_type=ctype,
                size=size,
                last_modified=lmod,
                etag=etag,
            )
        )
    return out


def walk_pdfs(start_path: str) -> Iterable[DavEntry]:
    stack = [start_path.strip("/")]
    seen = set()

    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)

        url = safe_join(BASE, current)
        entries = propfind(url, depth="1")

        for e in entries:
            if e.path.strip("/") == current.strip("/"):
                continue

            if e.is_dir:
                stack.append(e.path)
            else:
                if (e.content_type and "pdf" in e.content_type.lower()) or e.path.lower().endswith(".pdf"):
                    yield e


def download_file(rel_path: str, timeout: int = 120) -> bytes:
    url = safe_join(BASE, rel_path)
    r = requests.get(url, auth=_auth(), timeout=timeout)
    r.raise_for_status()
    return r.content


def list_directories(base_path: str = ""):
    """List immediate sub-directories under base_path (WebDAV).

    Returns list of folder paths (no trailing slash), relative to the WebDAV root (BASE).
    """
    base_path = (base_path or "").strip("/")
    url = safe_join(BASE, base_path)
    entries = propfind(url, depth="1")
    dirs = []
    for e in entries:
        if e.path.strip("/") == base_path:
            continue
        if e.is_dir:
            dirs.append(e.path.strip("/"))
    return sorted(set(dirs))

def list_directories_recursive(base_path: str = "", max_depth: int = 6):
    """Recursively list directories under base_path up to max_depth."""
    base_path = (base_path or "").strip("/")
    out = set()
    frontier = [(base_path, 0)]
    while frontier:
        cur, d = frontier.pop()
        if d >= max_depth:
            continue
        try:
            subs = list_directories(cur)
        except Exception:
            subs = []
        for s in subs:
            if s not in out:
                out.add(s)
                frontier.append((s, d + 1))
    return sorted(out)
