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

import time
import random
import math
import os
import re
import json
import net

from net import Net
from rdioradio import RdioRadio

from urlparse import urlparse, parse_qs
from pyamf.remoting.client import RemotingService

from rdioapi import Rdio, RdioProtocolException, RdioAPIException
from useragent import getUserAgent


class RdioApi:
  _RDIO_API_ENDPOINT = 'https://www.rdio.com/api/1'
  _AMF_ENDPOINT = _RDIO_API_ENDPOINT + '/amf/'
  _STATE_FILE_NAME = 'rdio-state.json'
  _RDIO_DOMAIN = 'localhost'
  _RDIO_PLAYBACK_SECRET = "6JSuiNxJ2cokAK9T2yWbEOPX"
  _RDIO_PLAYBACK_SECRET_SEED = 5381
  _INITIAL_STATE = {'rdio_api': {'auth_state': {}}, 'playback_token': None, 'current_user': None, 'rdio_cookie': None, 'authorization_key': None}


  @staticmethod
  def debug(statement):
	  print statement


  def __init__(self):
    self._cookie_file = os.path.join('rdio_cookies.txt')
    self._net = Net(user_agent = getUserAgent(), cookie_file = self._cookie_file)
    self.debug('Persistent auth state not loaded')
    self._state = self._INITIAL_STATE
    self._init_rdio()
    self.authenticate()
    radio = RdioRadio(self)
    radio.start_radio("r139688", None)
    track = radio.next_track()
    if track:
      print "Play"
      print track['key']
      stream_url = self.resolve_playback_url(track['key'])
      if stream_url:
        print "Play this"
        print stream_url		

      
    
    
    
    

  def _init_rdio(self):
    self._rdio = Rdio('by3ypa9tdw5qbmbthk6x89yf', 'HNMaWqBTND', self._state['rdio_api'])


  def authenticate(self):
    self.debug("Authenticating to Rdio")
    try:
      auth_url = self._rdio.begin_authentication('oob')
    except RdioProtocolException, rpe:
      self.debug('Rdio begin_authentication failed: ' + str(rpe))
      raise RdioAuthenticationException('Check your API credentials in plugin settings')

    parsed_auth_url = urlparse(auth_url)
    parsed_params = parse_qs(parsed_auth_url.query)
    oauth_token = parsed_params['oauth_token'][0]

    self.debug("Authorizing OAuth token")
    oauth_state = self.call_direct('getOAuth1State', token = oauth_token)
    verifier = oauth_state['verifier']
    self.call_direct('approveOAuth1App', token = oauth_token, verifier = verifier)
    self.debug("Appoved oauth token")

    self.debug("Extracting Rdio cookie")
    self._state['rdio_cookie'] = self._net.get_cookies()['.rdio.com']['/']['r'].value
    self._state['rdio_cookie'] = '.eJyrVorPyU9OzElVslJQSs1T0lFQigexjQ1NTc0sjcxA_FIg39DCCChkYAnilwH5BrUAvXEOGg.9G6g7Q_SSvlPMzhL81TvUMKUJx0'

    self.debug("Verifying OAuth token on Rdio API")
    self._rdio.complete_authentication(verifier)

    self.debug("Getting playback token")
    self._state['playback_token'] = self._rdio.call('getPlaybackToken', domain=self._RDIO_DOMAIN)

    self.debug("Getting current user")
    self._state['current_user'] = self._rdio.call('currentUser')['key']

    self._save_state()
    self.debug("Successfully authenticated to Rdio")


  def logout(self):
    self.debug("Logging out from Rdio")
    self._rdio.logout()
    self._state = self._INITIAL_STATE
    self._save_state()
    self._init_rdio()
    self.debug("Successfully logged out from Rdio")


  def authenticated(self):
    return self._rdio.authenticated \
      and'current_user' in self._state and self._state['current_user'] \
      and 'rdio_cookie' in self._state and self._state['rdio_cookie']  \
      and self._state['playback_token']


  def resolve_playback_url(self, key):
    playback_url = None
    stream_mode = 1;

    if not stream_mode:
      playback_url = self._resolve_rtmp_playback_url_via_flash(key)
    elif stream_mode == 1:
      playback_url = self._resolve_rtmp_playback_url_via_http(key)
    else:
      playback_url = self._resolve_http_playback_url_via_http(key)

    return playback_url


  def _resolve_rtmp_playback_url_via_flash(self, key):
    self.debug("Resolving rtmp playback url for %s using flash" % key)
    user_agent = getUserAgent()
    self.debug("Using user agent '%s'" % user_agent)
    svc = RemotingService(self._AMF_ENDPOINT, amf_version = 0, user_agent = user_agent)
    svc.addHTTPHeader('Cookie', 'r=' + self._state['rdio_cookie'])
    svc.addHTTPHeader('Host', 'www.rdio.com')
    rdio_svc = svc.getService('rdio')

    playback_token = self._state['playback_token']
    secret_string = key + playback_token + self._RDIO_PLAYBACK_SECRET
    secret = self._RDIO_PLAYBACK_SECRET_SEED
    for c in secret_string:
        secret = ((secret << 5) + secret + ord(c)) % 65536;

    playerName = 'api_%s' % str(int(math.floor(random.random() * 1000000)))

    pi = rdio_svc.getPlaybackInfo({
        'domain': self._RDIO_DOMAIN,
        'playbackToken': playback_token,
        'manualPlay': False,
        'requiresUnlimited': False,
        'playerName': playerName,
        'type': 'flash',
        'secret': secret,
        'key': key})
    if not pi:
        raise Exception, 'Failed to get playback info'

    return self._extract_rtmp_url_from_playback_info(pi)


  def _resolve_rtmp_playback_url_via_http(self, key):
    self.debug("Resolving rtmp playback url for %s using web" % key)
    pi = self._get_playback_info_via_http(key, 'flash')
    return self._extract_rtmp_url_from_playback_info(pi)


  def _resolve_http_playback_url_via_http(self, key):
    self.debug("Resolving HTTP playback url for %s using web" % key)
    pi = self._get_playback_info_via_http(key, 'web')
    stream_url = pi['surl']
    self.debug("Resolved playback URL for key '%s' to %s" % (key, stream_url))
    return stream_url


  def _get_playback_info_via_http(self, key, streaming_type = 'web'):
    return self.call_direct('getPlaybackInfo',
      requiresUnlimited = False,
      manualPlay = False,
      key = key,
      type = streaming_type,
      playerName = 'api_%s' % str(int(math.floor(random.random() * 1000000))))

  def current_user(self):
    return self._state['current_user']


  def call(self, method, **args):
    if not self.authenticated():
      self.authenticate()

    start_time = time.clock()
    self.debug("Executing Rdio API call '%s' with args %s" % (method, args))
    result = self._rdio.call(method, **args)
    self.debug("Rdio API response: " + str(result))
    time_ms = (time.clock() - start_time) * 1000
    self.debug("Executed Rdio API call %s in %i ms" % (method, time_ms))
    return result


  def call_direct(self, method, **args):
    '''
    Calls an Rdio API method directly through Python HTTP rather than through the Rdio API library.
    This technique requires us to log in on the Rdio home page to get an authorization key. It does,
    however, allow us to call undocumented API methods that aren't allowed through the usual API.
    '''
    if not self._state['authorization_key']:
      self._login()

    start_time = time.clock()
    self.debug("Executing Rdio direct API call '%s'" % method)
    request_args = {
      'method': method,
      '_authorization_key': self._state['authorization_key']
    }

    request_args.update(args)
    http_response = self._net.http_POST(self._RDIO_API_ENDPOINT + '/' + method, request_args)
    response = json.loads(http_response.content)
    self.debug("Rdio API response: " + str(response))
    time_ms = (time.clock() - start_time) * 1000
    self.debug("Executed Rdio direct API call %s in %i ms" % (method, time_ms))

    if response['status'] == 'ok':
      return response['result']
    else:
      raise RdioAPIException(response['message'])


  def _login(self):
    self.debug("Logging in to Rdio")

    http_response = self._net.http_GET('https://www.rdio.com/account/signin/')
    self._state['authorization_key'] = self._extract_authorization_key(http_response.content)
    self.debug("Retrieved signin page")

    username = ''
    password = ''
    response = self.call_direct('signIn', username = username, password = password, remember = '1')
    redirect_url = response['redirect_url']
    self.debug("Signin successful, redirect URL is %s" % redirect_url)

    http_response = self._net.http_GET(redirect_url)
    self._state['authorization_key'] = self._extract_authorization_key(http_response.content)
    self._net.save_cookies(self._cookie_file)
    self._save_state()
    self.debug("Login successful")


  def _extract_authorization_key(self, text):
    result = None
    authorizationKeyMatch = re.search(r'"authorizationKey": "([^"]+)"', text)
    if authorizationKeyMatch:
      result = authorizationKeyMatch.group(1)
    else:
      self.debug("Unable to find authorization key on signin page:\n" + text)
      raise RdioAuthenticationException("Unable to find authorization key")

    return result


  def _extract_rtmp_url_from_playback_info(self, pi):
    if not pi['canStream']:
      self.debug('Streaming key %s is not allowed' % pi['key'])
      return None

    rtmp_info = {
      'rtmp': 'rtmpe://%s:1935%s' % (pi['streamHost'], pi['streamApp']),
      'app': pi['streamApp'][1:],
      'playpath': 'mp3:%s' % pi['surl']
    }

    stream_url = rtmp_info['rtmp']
    for key, value in rtmp_info.items():
      stream_url += '' if key == 'rtmp' else ' %s=%s' % (key, value)

    self.debug("Resolved playback URL for key '%s' to %s" % (pi['key'], stream_url))
    return stream_url



  def _save_state(self):
    self.debug('Saving')


class RdioAuthenticationException(Exception):
  pass
