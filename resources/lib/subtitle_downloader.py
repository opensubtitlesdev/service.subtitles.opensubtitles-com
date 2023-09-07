
import os
import shutil
import sys
import uuid

import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

import xbmc
import re

from resources.lib.data_collector import get_language_data, get_media_data, get_file_path, convert_language, \
    clean_feature_release_name, get_flag
from resources.lib.exceptions import AuthenticationError, ConfigurationError, DownloadLimitExceeded, ProviderError, \
    ServiceUnavailable, TooManyRequests
from resources.lib.file_operations import get_file_data
from resources.lib.os.provider import OpenSubtitlesProvider
from resources.lib.utilities import get_params, log, error

__addon__ = xbmcaddon.Addon()
__scriptid__ = __addon__.getAddonInfo("id")

__profile__ = xbmcvfs.translatePath(__addon__.getAddonInfo("profile"))
__temp__ = xbmcvfs.translatePath(os.path.join(__profile__, "temp", ""))

if xbmcvfs.exists(__temp__):
    shutil.rmtree(__temp__)
xbmcvfs.mkdirs(__temp__)


class SubtitleDownloader:

    def __init__(self):

        self.api_key = __addon__.getSetting("APIKey")
        self.username = __addon__.getSetting("OSuser")
        self.password = __addon__.getSetting("OSpass")

        log(__name__, sys.argv)

        self.sub_format = "srt"
        self.handle = int(sys.argv[1])
        self.params = get_params()
        self.query = {}
        self.subtitles = {}
        self.file = {}

        try:
            self.open_subtitles = OpenSubtitlesProvider(self.api_key, self.username, self.password)
        except ConfigurationError as e:
            error(__name__, 32002, e)

    def handle_action(self):
        log(__name__, "action '%s' called" % self.params["action"])
        if self.params["action"] == "manualsearch":
            self.search(self.params['searchstring'])
        elif self.params["action"] == "search":
            self.search()
        elif self.params["action"] == "download":
            self.download()

    def search(self, query=""):
        file_data = get_file_data(get_file_path())
        language_data = get_language_data(self.params)

        log(__name__, "file_data '%s' " % file_data)
        log(__name__, "language_data '%s' " % language_data)

        # if there's query passed we use it, don't try to pull media data from VideoPlayer
        if query:
            media_data = {"query": query}
        else:
            media_data = get_media_data()
            if "basename" in file_data:
                media_data["query"] = file_data["basename"]
            log(__name__, "media_data '%s' " % media_data)

        self.query = {**media_data, **file_data, **language_data}

        try:
            self.subtitles = self.open_subtitles.search_subtitles(self.query)
        # TODO handle errors individually. Get clear error messages to the user
        except (TooManyRequests, ServiceUnavailable, ProviderError, ValueError) as e:
            error(__name__, 32001, e)

        if self.subtitles and len(self.subtitles):
            log(__name__, len(self.subtitles))
            self.list_subtitles()
        else:
            # TODO retry using guessit???
            log(__name__, "No subtitle found")

    def download(self):
        valid = 1
        try:
            self.file = self.open_subtitles.download_subtitle(
                {"file_id": self.params["id"], "sub_format": self.sub_format})
        # TODO handle errors individually. Get clear error messages to the user
            log(__name__, "XYXYXX download '%s' " % self.file)
        except AuthenticationError as e:
            error(__name__, 32003, e)
            valid = 0
        except DownloadLimitExceeded as e:
            log(__name__, f"XYXYXX limit excedded, username: {self.username}  {e}")
            if self.username=="":
                error(__name__, 32006, e)
            else:
                error(__name__, 32004, e)
            valid = 0
        except (TooManyRequests, ServiceUnavailable, ProviderError, ValueError) as e:
            error(__name__, 32001, e)
            valid = 0

        subtitle_path = os.path.join(__temp__, f"{str(uuid.uuid4())}.{self.sub_format}")
       
        if (valid==1):
            tmp_file = open(subtitle_path, "w" + "b")
            tmp_file.write(self.file["content"])
            tmp_file.close()
        

        list_item = xbmcgui.ListItem(label=subtitle_path)
        xbmcplugin.addDirectoryItem(handle=self.handle, url=subtitle_path, listitem=list_item, isFolder=False)

        return

        """old code"""
        # subs = Download(params["ID"], params["link"], params["format"])
        # for sub in subs:
        #    listitem = xbmcgui.ListItem(label=sub)
        #    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=sub, listitem=listitem, isFolder=False)

    def list_subtitles(self):
        """TODO rewrite using new data. do not forget Series/Episodes"""
        from difflib import SequenceMatcher

        release_groups = [
            ['bluray', 'bd', 'bdrip', 'brrip', 'bdmv', 'bdscr', 'remux', 'bdremux', 'uhdremux', 'uhdbdremux', 'uhdbluray'],
            ['web', 'webdl', 'webrip', 'webr', 'webdlrip', 'webcap'],
            ['dvd', 'dvd5', 'dvd9', 'dvdr', 'dvdrip', 'dvdscr'],
            ['scr', 'screener', 'r5', 'r6']
        ]
        release = []
        for group in release_groups:
            release.extend(group)
        release.extend(['avi', 'mp4', 'mkv', 'ts', 'm2ts', 'mts', 'mpeg', 'mpg', 'mov', 'wmv', 'flv', 'vob'])

        quality_groups = [
            ['4k', '2160p', '2160', '4kuhd', '4kultrahd', 'ultrahd', 'uhd'],
            ['1080p', '1080'],
            ['720p', '720'],
            ['480p'],
            ['360p', '240p', '144p'],
        ]
        quality = []
        for group in quality_groups:
            quality.extend(group)

        service_groups = [
            ['netflix', 'nflx', 'nf'],
            ['amazon', 'amzn', 'primevideo'],
            ['hulu', 'hlu'],
            ['crunchyroll', 'cr'],
            ['disney', 'disneyplus'],
            ['hbo', 'hbonow', 'hbogo', 'hbomax', 'hmax'],
            ['bbc'],
            ['sky', 'skyq'],
            ['syfy'],
            ['atvp', 'atvplus'],
            ['pcok', 'peacock'],
        ]
        service = []
        for group in service_groups:
            service.extend(group)

        codec_groups = [
            ['x264', 'h264', '264', 'avc'],
            ['x265', 'h265', '265', 'hevc'],
            ['av1', 'vp9', 'vp8', 'divx', 'xvid'],
        ]
        codec = []
        for group in codec_groups:
            codec.extend(group)

        audio_groups = [
            ['dts', 'dtshd', 'atmos', 'truehd'],
            ['aac', 'ac'],
            ['dd', 'ddp', 'ddp5', 'dd5', 'dd2', 'dd1', 'dd7', 'ddp7'],
        ]
        audio = []
        for group in audio_groups:
            audio.extend(group)

        color_groups = [
            ['hdr', '10bit', '12bit', 'hdr10', 'hdr10plus', 'dolbyvision', 'dolby', 'vision'],
            ['sdr', '8bit'],
        ]
        color = []
        for group in color_groups:
            color.extend(group)

        extra = ['extended', 'cut', 'remastered', 'proper']
        video_info = xbmc.Player().getPlayingFile()
        filename = (video_info).lower()
        regexsplitwords = r'[\s\.\:\;\(\)\[\]\{\}\\\/\&\€\'\`\#\@\=\$\?\!\%\+\-\_\*\^]'
        nameparts = re.split(regexsplitwords, filename)

        release_list = [i for i in nameparts if i in release]
        quality_list = [i for i in nameparts if i in quality]
        service_list = [i for i in nameparts if i in service]
        codec_list = [i for i in nameparts if i in codec]
        audio_list = [i for i in nameparts if i in audio]
        color_list = [i for i in nameparts if i in color]
        extra_list = [i for i in nameparts if i in extra]

        for item in release_list:
            for group in release_groups:
                if item in group:
                    release_list = group
                    break

        for item in quality_list:
            for group in quality_groups:
                if item in group:
                    quality_list = group
                    break

        for item in service_list:
            for group in service_groups:
                if item in group:
                    service_list = group
                    break

        for item in codec_list:
            for group in codec_groups:
                if item in group:
                    codec_list = group
                    break

        for item in audio_list:
            for group in audio_groups:
                if item in group:
                    audio_list = group
                    break

        for item in color_list:
            for group in color_groups:
                if item in group:
                    color_list = group
                    break

        sorted_subtitles = []

        for subtitle in self.subtitles:
            attributes = subtitle["attributes"]
            language = convert_language(attributes["language"], True)
            log(__name__, attributes)
            clean_name = clean_feature_release_name(attributes["feature_details"]["title"], attributes["release"],
                                                    attributes["feature_details"]["movie_name"])
            list_item = xbmcgui.ListItem(label=language,
                                         label2=clean_name)

            sorter = lambda x: (
                -sum(word in attributes["release"].lower() for word in release_list)*10,
                -sum(word in attributes["release"].lower() for word in service_list)*10,
                -sum(word in attributes["release"].lower() for word in quality_list)*5,
                -sum(word in attributes["release"].lower() for word in audio_list)*2,
                -sum(word in attributes["release"].lower() for word in codec_list)*2,
                -sum(word in attributes["release"].lower() for word in extra_list)*2,
                -sum(word in attributes["release"].lower() for word in color_list)*2,
                -SequenceMatcher(None, attributes["release"].lower(),(filename).lower()).ratio(),
                )

            list_item.setArt({
                "icon": str(int(round(float(attributes["ratings"]) / 2))),
                "thumb": get_flag(attributes["language"])})
            list_item.setProperty("sync", "true" if ("moviehash_match" in attributes and attributes["moviehash_match"]) else "false")
            list_item.setProperty("hearing_imp", "true" if attributes["hearing_impaired"] else "false")
            """TODO take care of multiple cds id&id or something"""
            url = f"plugin://{__scriptid__}/?action=download&id={attributes['files'][0]['file_id']}"
            sorted_subtitles.append((list_item, sorter(list_item)))

    # Sort the list of subtitles based on the sorting key
        sorted_subtitles.sort(key=lambda item: item[1])

    # Add sorted subtitles to the directory
        for sorted_item, _ in sorted_subtitles:
            xbmcplugin.addDirectoryItem(handle=self.handle, url=sorted_item.getProperty("url"), listitem=sorted_item, isFolder=False)

        xbmcplugin.endOfDirectory(self.handle)
