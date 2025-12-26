# Configuration for accessing the public ownCloud share.
#
# Two supported modes:
# 1) Public Files WebDAV (token is in the URL; typically no basic auth):
#    BASE = https://<host>/owncloud/remote.php/dav/public-files/<SHARE_TOKEN>
#
# 2) Public Share WebDAV (basic auth required):
#    BASE = https://<host>/owncloud/public.php/webdav
#    AUTH username = SHARE_TOKEN, password = SHARE_PASSWORD (often empty if no password)
#
# Set USE_PUBLIC_SHARE_WEBDAV=True to force mode (2).
#
SHARE_TOKEN = "sRjA0sPnknwxmjx"

# If the share link is password-protected, set it here.
# If there is no password, keep it as empty string.
SHARE_PASSWORD = ""

# Default to the public share WebDAV endpoint (Basic Auth) to avoid 401s
USE_PUBLIC_SHARE_WEBDAV = True

if USE_PUBLIC_SHARE_WEBDAV:
    BASE = "https://fedecanat.es/owncloud/public.php/webdav"
else:
    BASE = f"https://fedecanat.es/owncloud/remote.php/dav/public-files/{SHARE_TOKEN}"

NS = {
    "d": "DAV:",
    "oc": "http://owncloud.org/ns",
    "s": "http://sabredav.org/ns",
}

PROPFIND_BODY = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <d:resourcetype />
    <d:getcontenttype />
    <d:getcontentlength />
    <d:getlastmodified />
    <d:getetag />
    <oc:fileid />
  </d:prop>
</d:propfind>
"""
