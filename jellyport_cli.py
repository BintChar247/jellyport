#!/usr/bin/env python3
"""
jellyport_cli.py - Jellyport command line: copy Plex video playlists to Jellyfin.

Both servers usually point at the same media files (e.g. on a NAS),
so items are matched in this order:
  1. File path (after applying the path_mappings from config.json)
  2. Provider IDs (IMDb / TMDb / TVDb)
  3. Title + year
  4. File name (when unique)

Standard library only - no pip install needed.

Usage:
  python jellyport_cli.py --list                  # show Plex playlists
  python jellyport_cli.py --dry-run               # preview everything
  python jellyport_cli.py                         # copy all playlists
  python jellyport_cli.py -p "Date Night" -p "Marvel"
  python jellyport_cli.py --replace               # rebuild existing playlists
"""

__version__ = "1.0.0"

import argparse
import json
import os
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

PAGE_SIZE = 500


class ApiError(Exception):
    """Raised for any server / network problem."""


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
class Http:
    def __init__(self, base_url, headers, verify_ssl=True, timeout=60):
        self.base = base_url.rstrip("/")
        self.headers = headers
        self.timeout = timeout
        self.ctx = None
        if not verify_ssl:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def request(self, method, path, params=None, body=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise ApiError(f"HTTP {e.code} on {method} {path}: {detail}")
        except urllib.error.URLError as e:
            raise ApiError(f"Could not reach {self.base}: {e.reason}")
        except (TimeoutError, OSError) as e:
            raise ApiError(f"Could not reach {self.base}: {e}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def get(self, path, params=None):
        return self.request("GET", path, params)


# --------------------------------------------------------------------------- #
# Normalisation / matching helpers
# --------------------------------------------------------------------------- #
def norm_path(p):
    if not p:
        return ""
    p = p.replace("\\", "/")
    p = re.sub(r"/+", "/", p)
    return unicodedata.normalize("NFC", p).lower()


def norm_title(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("&", "and")
    t = re.sub(r"^(the|a|an)\s+", "", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def apply_mappings(path, mappings):
    """Translate a Plex-side path into the Jellyfin-side path."""
    np = norm_path(path)
    for m in mappings:
        src = norm_path(m["plex"]).rstrip("/")
        dst = norm_path(m["jellyfin"]).rstrip("/")
        if np == src or np.startswith(src + "/"):
            return dst + np[len(src):]
    return np


def basename(path):
    return norm_path(path).rsplit("/", 1)[-1]


def plex_guids(item):
    """Return {'imdb': 'tt123', 'tmdb': '456', ...} from a Plex item."""
    ids = {}
    for g in item.get("Guid", []) or []:
        gid = g.get("id", "")
        if "://" in gid:
            k, v = gid.split("://", 1)
            ids[k.lower()] = v.lower()
    # Legacy agents put it in item['guid'], e.g. com.plexapp.agents.imdb://tt123?lang=en
    legacy = item.get("guid", "")
    m = re.match(r"com\.plexapp\.agents\.(\w+)://([^?/]+)", legacy)
    if m:
        k = {"themoviedb": "tmdb", "thetvdb": "tvdb"}.get(m.group(1), m.group(1))
        ids.setdefault(k, m.group(2).lower())
    return ids


# --------------------------------------------------------------------------- #
# Plex
# --------------------------------------------------------------------------- #
class Plex:
    def __init__(self, cfg):
        self.http = Http(
            cfg["url"],
            {"X-Plex-Token": cfg["token"], "Accept": "application/json"},
            cfg.get("verify_ssl", True),
        )

    def playlists(self):
        data = self.http.get("/playlists", {"playlistType": "video"})
        return data["MediaContainer"].get("Metadata", []) or []

    def playlist_items(self, rating_key):
        items, start = [], 0
        while True:
            data = self.http.get(
                f"/playlists/{rating_key}/items",
                {
                    "includeGuids": 1,
                    "X-Plex-Container-Start": start,
                    "X-Plex-Container-Size": PAGE_SIZE,
                },
            )
            mc = data["MediaContainer"]
            batch = mc.get("Metadata", []) or []
            items.extend(batch)
            start += len(batch)
            total = mc.get("totalSize", mc.get("size", 0))
            if not batch or start >= total:
                return items

    def sections(self):
        data = self.http.get("/library/sections")
        return data["MediaContainer"].get("Directory", []) or []

    def section_items(self, key):
        """All movies in a library section."""
        items, start = [], 0
        while True:
            data = self.http.get(
                f"/library/sections/{key}/all",
                {
                    "type": 1,
                    "includeGuids": 1,
                    "X-Plex-Container-Start": start,
                    "X-Plex-Container-Size": PAGE_SIZE,
                },
            )
            mc = data["MediaContainer"]
            batch = mc.get("Metadata", []) or []
            items.extend(batch)
            start += len(batch)
            total = mc.get("totalSize", mc.get("size", 0))
            if not batch or start >= total:
                return items


# --------------------------------------------------------------------------- #
# Jellyfin
# --------------------------------------------------------------------------- #
class Jellyfin:
    def __init__(self, cfg):
        token = cfg["api_key"]
        self.http = Http(
            cfg["url"],
            {
                "Authorization": f'MediaBrowser Client="Jellyport", Device="Jellyport", '
                                 f'DeviceId="jellyport", Version="{__version__}", '
                                 f'Token="{token}"',
                "X-Emby-Token": token,
                "Accept": "application/json",
            },
            cfg.get("verify_ssl", True),
        )
        self.user_id = self._resolve_user(cfg["user"])

    def _resolve_user(self, name):
        users = self.http.get("/Users") or []
        for u in users:
            if u["Name"].lower() == name.lower():
                return u["Id"]
        names = ", ".join(u["Name"] for u in users)
        raise ApiError(f"Jellyfin user '{name}' not found. Available: {names}")

    def _paged_items(self, params):
        out, start = [], 0
        while True:
            p = dict(params, userId=self.user_id, StartIndex=start, Limit=PAGE_SIZE)
            data = self.http.get("/Items", p)
            batch = data.get("Items", [])
            out.extend(batch)
            start += len(batch)
            if not batch or start >= data.get("TotalRecordCount", 0):
                return out

    def library(self):
        return self._paged_items({
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Episode,Video,MusicVideo",
            "Fields": "Path,ProviderIds,ProductionYear,MediaSources",
        })

    def playlists(self):
        return self._paged_items({"Recursive": "true", "IncludeItemTypes": "Playlist"})

    def playlist_items(self, playlist_id):
        data = self.http.get(f"/Playlists/{playlist_id}/Items",
                             {"userId": self.user_id, "Fields": "ProductionYear"})
        return (data or {}).get("Items", [])

    def playlist_item_ids(self, playlist_id):
        return [i["Id"] for i in self.playlist_items(playlist_id)]

    def create_playlist(self, name, ids):
        return self.http.request("POST", "/Playlists", body={
            "Name": name, "Ids": ids, "UserId": self.user_id, "MediaType": "Video",
        })

    def add_to_playlist(self, playlist_id, ids):
        for i in range(0, len(ids), 100):  # keep the query string short
            self.http.request("POST", f"/Playlists/{playlist_id}/Items",
                              {"ids": ",".join(ids[i:i + 100]), "userId": self.user_id})

    def delete_item(self, item_id):
        self.http.request("DELETE", f"/Items/{item_id}")


# --------------------------------------------------------------------------- #
# Matcher
# --------------------------------------------------------------------------- #
class Matcher:
    def __init__(self, jf_items, mappings):
        self.mappings = mappings
        self.by_path, self.by_file, self.by_pid, self.by_title = {}, {}, {}, {}
        for it in jf_items:
            paths = {it.get("Path")}
            for ms in it.get("MediaSources") or []:
                paths.add(ms.get("Path"))
            for p in filter(None, paths):
                self.by_path.setdefault(norm_path(p), it)
                self.by_file.setdefault(basename(p), []).append(it)
            for k, v in (it.get("ProviderIds") or {}).items():
                if v:
                    self.by_pid.setdefault((k.lower(), str(v).lower()), it)
            if it.get("Type") == "Movie":
                key = (norm_title(it.get("Name")), it.get("ProductionYear"))
                self.by_title.setdefault(key, it)

    def match(self, px):
        files = [
            part.get("file")
            for media in px.get("Media", []) or []
            for part in media.get("Part", []) or []
            if part.get("file")
        ]
        # 1. exact path after mapping
        for f in files:
            hit = self.by_path.get(apply_mappings(f, self.mappings))
            if hit:
                return hit, "path"
        # 2. provider IDs
        for k, v in plex_guids(px).items():
            hit = self.by_pid.get((k, v))
            if hit:
                return hit, k
        # 3. title + year (movies)
        if px.get("type") == "movie":
            y = px.get("year")
            t = norm_title(px.get("title"))
            for year in (y, (y or 0) - 1, (y or 0) + 1):
                hit = self.by_title.get((t, year))
                if hit:
                    return hit, "title"
        # 4. unique filename
        for f in files:
            cands = self.by_file.get(basename(f), [])
            if len(cands) == 1:
                return cands[0], "filename"
        return None, None


def describe(px):
    if px.get("type") == "episode":
        return (f'{px.get("grandparentTitle")} S{px.get("parentIndex", 0):02d}'
                f'E{px.get("index", 0):02d} - {px.get("title")}')
    return f'{px.get("title")} ({px.get("year", "?")})'


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_config(path):
    if not os.path.exists(path):
        raise SystemExit(f"Config file '{path}' not found. Copy config.example.json "
                         "to config.json and fill it in.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Jellyport: copy Plex video playlists to Jellyfin.")
    ap.add_argument("--version", action="version", version=f"Jellyport {__version__}")
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("-p", "--playlist", action="append",
                    help="Only copy this playlist (repeatable). Default: all.")
    ap.add_argument("--list", action="store_true", help="List Plex playlists and exit.")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen; change nothing.")
    ap.add_argument("--replace", action="store_true",
                    help="Delete and recreate Jellyfin playlists that already exist "
                         "(default: only add missing items).")
    ap.add_argument("--include-smart", action="store_true",
                    help="Also copy Plex smart playlists (as a static snapshot).")
    ap.add_argument("--prefix", default="", help="Prefix for Jellyfin playlist names.")
    args = ap.parse_args()

    cfg = load_config(args.config)
    plex = Plex(cfg["plex"])
    playlists = plex.playlists()

    if args.list:
        for pl in playlists:
            smart = " [smart]" if pl.get("smart") else ""
            print(f'{pl["title"]}  ({pl.get("leafCount", "?")} items){smart}')
        return

    if args.playlist:
        wanted = {n.lower() for n in args.playlist}
        playlists = [p for p in playlists if p["title"].lower() in wanted]
        missing = wanted - {p["title"].lower() for p in playlists}
        for m in missing:
            print(f"! Plex playlist not found: {m}")
    if not args.include_smart:
        skipped = [p["title"] for p in playlists if p.get("smart")]
        playlists = [p for p in playlists if not p.get("smart")]
        for s in skipped:
            print(f"- Skipping smart playlist '{s}' (use --include-smart)")
    if not playlists:
        print("Nothing to do.")
        return

    jf = Jellyfin(cfg["jellyfin"])
    print("Loading Jellyfin library...", flush=True)
    matcher = Matcher(jf.library(), cfg.get("path_mappings", []))
    existing = {p["Name"].lower(): p for p in jf.playlists()}

    total_unmatched = []
    for pl in playlists:
        name = args.prefix + pl["title"]
        print(f'\n=== {pl["title"]} -> "{name}"')
        items = plex.playlist_items(pl["ratingKey"])

        ids, seen = [], set()
        for px in items:
            hit, how = matcher.match(px)
            if hit:
                if hit["Id"] not in seen:
                    ids.append(hit["Id"])
                    seen.add(hit["Id"])
                print(f"  ok   [{how:8}] {describe(px)}")
            else:
                print(f"  MISS            {describe(px)}")
                total_unmatched.append((pl["title"], describe(px)))

        print(f"  matched {len(ids)}/{len(items)}")
        if not ids:
            print("  nothing matched - skipping")
            continue

        current = existing.get(name.lower())
        if current and args.replace:
            print(f"  replacing existing Jellyfin playlist")
            if not args.dry_run:
                jf.delete_item(current["Id"])
            current = None

        if current:
            have = set(jf.playlist_item_ids(current["Id"]))
            new = [i for i in ids if i not in have]
            print(f"  playlist exists - adding {len(new)} missing item(s)")
            if new and not args.dry_run:
                jf.add_to_playlist(current["Id"], new)
        else:
            print(f"  creating playlist with {len(ids)} item(s)")
            if not args.dry_run:
                # create with the first batch, then append the rest
                res = jf.create_playlist(name, ids[:100])
                if len(ids) > 100:
                    jf.add_to_playlist(res["Id"], ids[100:])

    if total_unmatched:
        print(f"\n{len(total_unmatched)} item(s) could not be matched:")
        for pl_name, d in total_unmatched:
            print(f"  [{pl_name}] {d}")
        print("Tip: check path_mappings in config.json, or make sure Jellyfin has "
              "scanned/identified these files.")
    if args.dry_run:
        print("\nDry run - no changes were made.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        sys.exit(1)
