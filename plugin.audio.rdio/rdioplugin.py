# Copyright 2012 Charles Blaxland
# This file is part of rdio-xbmc.
#
# rdio-xbmc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# rdio-xbmc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with rdio-xbmc.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import inspect
import time
import urllib
import rdiocommon

from rdioradio import RdioRadio


sys.path.append(os.path.join('resources', 'lib'))

from rdioxbmc import RdioApi, RdioAuthenticationException


class XbmcRdioOperation:
  _TYPE_ALBUM = 'a'
  _TYPE_ARTIST = 'r'
  _TYPE_PLAYLIST = 'p'
  _TYPE_USER = 's'
  _TYPE_TRACK = 't'
  _TYPE_ALBUM_IN_COLLECTION = 'al'
  _TYPE_ARTIST_IN_COLLECTION = 'rl'

  _PAGE_SIZE_ALBUMS = 100
  _PAGE_SIZE_HEAVY_ROTATION = 14

  def __init__(self):
    self._rdio_api = RdioApi()

  def main(self):

    # TODO should get rid of the recursive references to 'mode=main' here as they mess up the ".." nav

    if self._mandatory_settings_are_valid():
      if not self._rdio_api.authenticated():
        try:
          self._rdio_api.authenticate()
        except RdioAuthenticationException, rae:
          self._addon.show_error_dialog([self._addon.get_string(30903), str(rae)])

  def _add_tracks(self, tracks, show_artist = False, playlist_key = None, extra_queries = None):
    i = 0
    for track in tracks:

      context_menus = []

      if not 'playCount' in track:
        track['playCount'] = 0

      title = track['name']
      if show_artist:
        title += ' (%s)' % track['artist']
      if not track['canStream']:
        title += '  :('

      queries = {'mode': 'play', 'key': track['key']}
      if extra_queries:
        queries.update(extra_queries)

      self._addon.add_item(queries,
        {
          'title': title.encode('UTF-8'),
          'artist': track['artist'],
          'album': track['album'],
          'duration': track['duration'],
          'tracknumber': track['trackNum'],
          'playCount': track['playCount']
        },
        playlist = xbmc_playlist,
        item_type = 'music',
        contextmenu_items = context_menus,
        img = track['bigIcon'] if 'bigIcon' in track else track['icon'])

      i += 1



  def play(self, **params):
    key = params['key']
    stream_url = self._rdio_api.resolve_playback_url(key)
    if stream_url:
      print "Play this"
      print stream_url


  def add_to_collection(self, **params):
    key = params['key']
    if self._can_be_added_to_collection(key):
      track_keys= [key]
    else:
      track_keys = self._get_track_keys_not_in_collection(key)

    if track_keys:
      self._rdio_api.call('addToCollection', keys = ','.join(track_keys))

  def remove_from_collection(self, **params):
    key = params['key']
    if self._can_be_added_to_collection(key):
      track_keys= [key]
    else:
      track_keys = self._get_track_keys_in_collection(key)

    if track_keys:
      self._rdio_api.call('removeFromCollection', keys = ','.join(track_keys))

  def add_to_playlist(self, **params):
    playlist = self._get_user_selected_playlist()
    if playlist:
      self._rdio_api.call('addToPlaylist', playlist = playlist, tracks = params['key'])

  def remove_from_playlist(self, **params):
    track_to_remove = params['key']
    playlist = params['playlist']
    track_container = self._rdio_api.call('get', keys = playlist, extras = 'tracks')[playlist]
    i = 0
    index_to_remove = None
    for track in track_container['tracks']:
      if track['key'] == track_to_remove:
        index_to_remove = i
        break

      i += 1

    if index_to_remove:
      self._rdio_api.call('removeFromPlaylist', playlist = playlist, tracks = track_to_remove, index = index_to_remove, count = 1)


  def _get_user_selected_playlist(self):
    playlists = self._rdio_api.call('getPlaylists', extras = 'description')
    playlist_map = {}
    playlist_names = []
    for playlist in playlists['owned']:
      playlist_map[playlist['name']] = playlist['key']
      playlist_names.append(playlist['name'])

    for playlist in playlists['collab']:
      playlist_map[playlist['name']] = playlist['key']
      playlist_names.append(playlist['name'])

    dialog = xbmcgui.Dialog()
    selection = dialog.select("Select Playlist", playlist_names)
    result = None
    if selection >= 0:
      result = playlist_map[playlist_names[selection]]

    return result


  def _get_track_keys_in_collection(self, key):
    return self._get_track_keys(key, in_collection = True, not_in_collection = False)

  def _get_track_keys_not_in_collection(self, key):
    return self._get_track_keys(key, in_collection = False, not_in_collection = True)

  def _get_track_keys(self, key, in_collection = True, not_in_collection = True):
    track_keys = []
    track_container = self._rdio_api.call('get', keys = key, extras = 'tracks,Track.isInCollection')
    for track in track_container[key]['tracks']:
      if ((in_collection and track['isInCollection']) or (not_in_collection and not track['isInCollection'])):
        track_keys.append(track['key'])

    return track_keys


  def play_artist_radio(self, artist):
    radio = RdioRadio(self._rdio_api)
    radio.start_radio(artist, user)
    


  def _mandatory_settings_are_valid(self):
    return self._addon.get_setting('username') and self._addon.get_setting('password') and self._addon.get_setting('apikey') and self._addon.get_setting('apisecret')



  def execute(self):
    start_time = time.clock()
    time_ms = (time.clock() - start_time) * 1000


XbmcRdioOperation().execute()
