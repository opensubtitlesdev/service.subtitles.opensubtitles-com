from urllib.parse import unquote
from difflib import SequenceMatcher
import json
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon

from resources.lib.utilities import log, normalize_string

__addon__ = xbmcaddon.Addon()


def get_file_path():
    return xbmc.Player().getPlayingFile()


# ---------- Small helpers ----------

def _strip_imdb_tt(value):
    if not value:
        return None
    s = str(value).strip()
    if s.startswith("tt"):
        s = s[2:]
    return s if s.isdigit() else None


def _jsonrpc(method, params=None):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params:
            payload["params"] = params
        resp = xbmc.executeJSONRPC(json.dumps(payload))
        data = json.loads(resp)
        return data.get("result")
    except Exception as e:
        log(__name__, f"JSON-RPC error in {method}: {e}")
        return None


def get_media_data():

    item = {"query": None,
            "year": xbmc.getInfoLabel("VideoPlayer.Year"),
            "season_number": str(xbmc.getInfoLabel("VideoPlayer.Season")),
            "episode_number": str(xbmc.getInfoLabel("VideoPlayer.Episode")),
            "tv_show_title": normalize_string(xbmc.getInfoLabel("VideoPlayer.TVshowtitle")),
            "original_title": normalize_string(xbmc.getInfoLabel("VideoPlayer.OriginalTitle")),
            "parent_tmdb_id": None,
            "parent_imdb_id": None,
            "imdb_id": None,
            "tmdb_id": None}

    # ---------------- TV SHOW (Episode) ----------------
    if item["tv_show_title"]:
        item["tvshowid"] = xbmc.getInfoLabel("VideoPlayer.TvShowDBID")
        item["query"] = item["tv_show_title"]
        item["year"] = None  # Safer for OS search

        # 1) Pull parent IDs straight from InfoLabels (works even for non-library playback)
        try:
            # TMDb parent (Kodi 19+ has UniqueID labels)
            parent_tmdb_raw = xbmc.getInfoLabel("VideoPlayer.UniqueID(tmdb)")
            if parent_tmdb_raw and parent_tmdb_raw.isdigit():
                item["parent_tmdb_id"] = int(parent_tmdb_raw)
                log(__name__, f"Parent TMDb from InfoLabel: {item['parent_tmdb_id']}")

            # IMDb parent
            parent_imdb_raw = (xbmc.getInfoLabel("VideoPlayer.UniqueID(imdb)")
                               or xbmc.getInfoLabel("VideoPlayer.IMDBNumber")
                               or xbmc.getInfoLabel("ListItem.Property(TvShow.IMDBNumber)")
                               or xbmc.getInfoLabel("ListItem.IMDBNumber"))
            imdb_digits = _strip_imdb_tt(parent_imdb_raw)
            if imdb_digits and 6 <= len(imdb_digits) <= 8:
                item["parent_imdb_id"] = int(imdb_digits)
                log(__name__, f"Parent IMDb from InfoLabel: {item['parent_imdb_id']}")
        except Exception as e:
            log(__name__, f"Failed to read parent IDs from InfoLabels: {e}")

        # 2) If still missing, fall back to library JSON-RPC (when the show is in the library)
        if len(item["tvshowid"]) != 0 and (not item["parent_tmdb_id"] or not item["parent_imdb_id"]):
            try:
                TVShowDetails = xbmc.executeJSONRPC(
                    '{ "jsonrpc": "2.0", "id":"1", "method": "VideoLibrary.GetTVShowDetails", '
                    '"params":{"tvshowid":' + item["tvshowid"] + ', "properties": ["episodeguide", "imdbnumber"]} }'
                )
                TVShowDetails_dict = json.loads(TVShowDetails)
                if "result" in TVShowDetails_dict and "tvshowdetails" in TVShowDetails_dict["result"]:
                    tvshow_details = TVShowDetails_dict["result"]["tvshowdetails"]

                    # parent IMDb
                    if not item["parent_imdb_id"]:
                        imdb_raw = str(tvshow_details.get("imdbnumber") or "")
                        imdb_digits = _strip_imdb_tt(imdb_raw)
                        if imdb_digits and 6 <= len(imdb_digits) <= 8:
                            item["parent_imdb_id"] = int(imdb_digits)
                            log(__name__, f"Parent IMDb via JSON-RPC: {item['parent_imdb_id']}")

                    # parent TMDb (episodeguide)
                    if not item["parent_tmdb_id"]:
                        episodeguideXML = tvshow_details.get("episodeguide")
                        if episodeguideXML:
                            episodeguide = ET.fromstring(episodeguideXML)
                            if episodeguide.text:
                                guide_json = json.loads(episodeguide.text)
                                tmdb = guide_json.get("tmdb")
                                if tmdb and str(tmdb).isdigit():
                                    item["parent_tmdb_id"] = int(tmdb)
                                    log(__name__, f"Parent TMDb via JSON-RPC: {item['parent_tmdb_id']}")
            except (json.JSONDecodeError, ET.ParseError, ValueError, KeyError) as e:
                log(__name__, f"Failed to extract TV show IDs via JSON-RPC: {e}")

        # 3) Try to get the specific EPISODE IDs (optional but nice if present)
        try:
            ep_tmdb = xbmc.getInfoLabel("VideoPlayer.UniqueID(tmdbepisode)")
            if ep_tmdb and ep_tmdb.isdigit():
                item["tmdb_id"] = int(ep_tmdb)
                log(__name__, f"Episode TMDb from InfoLabel: {item['tmdb_id']}")
            ep_imdb = xbmc.getInfoLabel("VideoPlayer.UniqueID(imdbepisode)")
            ep_imdb_digits = _strip_imdb_tt(ep_imdb)
            if ep_imdb_digits and ep_imdb_digits.isdigit():
                item["imdb_id"] = int(ep_imdb_digits)
                log(__name__, f"Episode IMDb from InfoLabel: {item['imdb_id']}")
        except Exception as e:
            log(__name__, f"Failed to read episode IDs from InfoLabels: {e}")

    # ---------------- MOVIE ----------------
    elif item["original_title"]:
        item["query"] = item["original_title"]

        try:
            imdb_raw = (xbmc.getInfoLabel("VideoPlayer.UniqueID(imdb)")
                        or xbmc.getInfoLabel("VideoPlayer.IMDBNumber"))
            imdb_digits = _strip_imdb_tt(imdb_raw)
            if imdb_digits and 6 <= len(imdb_digits) <= 8:
                item["imdb_id"] = int(imdb_digits)
                log(__name__, f"Found IMDB ID for movie: {item['imdb_id']}")

            tmdb_raw = (xbmc.getInfoLabel("VideoPlayer.UniqueID(tmdb)")
                        or xbmc.getInfoLabel("VideoPlayer.DBID"))
            if tmdb_raw and str(tmdb_raw).isdigit():
                tmdb_id = int(tmdb_raw)
                if tmdb_id > 0:
                    item["tmdb_id"] = tmdb_id
                    log(__name__, f"Found TMDB ID for movie: {item['tmdb_id']}")
        except (ValueError, KeyError) as e:
            log(__name__, f"Failed to extract movie IDs: {e}")

    # ---------- Cleanup & precedence ----------
    for k in ("parent_tmdb_id", "parent_imdb_id", "tmdb_id", "imdb_id"):
        v = item.get(k)
        if v in (0, "0", "", None):
            item[k] = None

    # Prefer parent TMDb over parent IMDb for TV
    if item.get("parent_tmdb_id") and item.get("parent_imdb_id"):
        log(__name__, f"Both parent TMDB and IMDB IDs found, preferring TMDB ID: {item['parent_tmdb_id']}")
        item["parent_imdb_id"] = None

    # Prefer TMDb over IMDb for item-level IDs
    if item.get("tmdb_id") and item.get("imdb_id"):
        log(__name__, f"Both TMDB and IMDB IDs found for item, preferring TMDB ID: {item['tmdb_id']}")
        item["imdb_id"] = None

    if not item.get("query"):
        log(__name__, "query still blank, fallback to title")
        item["query"] = normalize_string(xbmc.getInfoLabel("VideoPlayer.Title"))

    # Specials handling
    if isinstance(item.get("episode_number"), str) and item["episode_number"] and item["episode_number"].lower().find("s") > -1:
        item["season_number"] = "0"
        item["episode_number"] = item["episode_number"][-1:]

    # Remove internal-only key
    if "tvshowid" in item:
        del item["tvshowid"]

    return item


def get_language_data(params):
    search_languages = unquote(params.get("languages")).split(",")
    search_languages_str = ""
    preferred_language = params.get("preferredlanguage")

    if preferred_language and preferred_language not in search_languages and preferred_language != "Unknown" and preferred_language != "Undetermined":
        search_languages.append(preferred_language)
        search_languages_str = search_languages_str + "," + preferred_language

    for language in search_languages:
        lang = convert_language(language)
        if lang:
            log(__name__, f"Language  found: '{lang}' search_languages_str:'{search_languages_str}")
            if search_languages_str == "":
                search_languages_str = lang
            else:
                search_languages_str = search_languages_str + "," + lang
        else:
            log(__name__, f"Language code not found: '{language}'")

    item = {
        "hearing_impaired": __addon__.getSetting("hearing_impaired"),
        "foreign_parts_only": __addon__.getSetting("foreign_parts_only"),
        "machine_translated": __addon__.getSetting("machine_translated"),
        "ai_translated": __addon__.getSetting("ai_translated"),
        "languages": search_languages_str
    }

    return item


def convert_language(language, reverse=False):
    language_list = {
        "English": "en",
        "Portuguese (Brazil)": "pt-br",
        "Portuguese": "pt-pt",
        "Chinese": "zh-cn",
        "Chinese (simplified)": "zh-cn",
        "Chinese (traditional)": "zh-tw"}

    reverse_language_list = {v: k for k, v in list(language_list.items())}

    if reverse:
        iterated_list = reverse_language_list
        xbmc_param = xbmc.ENGLISH_NAME
    else:
        iterated_list = language_list
        xbmc_param = xbmc.ISO_639_1

    if language in iterated_list:
        return iterated_list[language]
    else:
        return xbmc.convertLanguage(language, xbmc_param)


def get_flag(language_code):
    language_list = {
        "pt-pt": "pt",
        "pt-br": "pb",
        "zh-cn": "zh",
        "zh-tw": "-"
    }
    return language_list.get(language_code.lower(), language_code)


def clean_feature_release_name(title, release, movie_name=""):
    if not title:
        if not movie_name:
            if not release:
                raise ValueError("None of title, release, movie_name contains a string")
            return release
        else:
            if not movie_name[0:4].isnumeric():
                name = movie_name
            else:
                name = movie_name[7:]
    else:
        name = title

    match_ratio = SequenceMatcher(None, name, release).ratio()
    log(__name__, f"name: {name}, release: {release}, match_ratio: {match_ratio}")
    if name in release:
        return release
    elif match_ratio > 0.3:
        return release
    else:
        return f"{name} {release}"
