import sys
import os
import time
from io import BytesIO
from zipfile import ZipFile
import pypath
import requests
from kivy.logger import Logger
from kivy.resources import resource_add_path
from kivy.config import ConfigParser
from kivy.resources import resource_find
from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock

DEFAULT_HOST = '192.168.1.100'
DEFAULT_PORT = '5000'
TIMEOUT = (5, 20) # connect_timeout, read_timeout
SRC_URL = 'http://{host}:{port}/mobile/src.zip'

class Bootstrap(object):

    def __init__(self, root, local):
        Logger.info('bootstrap: root directory is %s', root)
        self.root = pypath.local(root)
        self.local = local
        self.src = self.root.join('src')

    def get_sync_server(self):
        ini = self.root.join('mcont.ini')
        Logger.info('bootstrap: config file is %s', ini)
        if ini.exists():
            config = ConfigParser()
            config.read(str(ini))
            host = config.get('server', 'host')
            port = config.get('server', 'port')
            Logger.info('bootstrap: using server %s:%s', host, port)
            return host, port
        else:
            Logger.info('bootstrap: using default server %s:%s', DEFAULT_HOST, DEFAULT_PORT)
            return DEFAULT_HOST, DEFAULT_PORT

    def update(self):
        if self.local:
            # nothing to do for local deployments
            Logger.info('bootstrap: local deployment, nothing to do')
            return True
        self.execute_remote_startup()
        resp = self.download()
        if resp:
            self.unpack_src(resp.content)
            return True
        else:
            return False

    def execute_remote_startup(self):
        host, port = self.get_sync_server()
        url = 'http://%s:%s/mobile/startup' % (host, port)
        Logger.info('bootstrap: downloading mobile/startup from %s', url)
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            Logger.error('bootstrap: cannot download mobile/startup: %s', e)
            return None
        else:
            Logger.info('bootstrap: got startup.py from server, exec()...')
            exec(resp.text)

    def download(self):
        host, port = self.get_sync_server()
        url = SRC_URL.format(host=host, port=port)
        Logger.info('bootstrap: downloading src.zip from %s', url)
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            Logger.error('bootstrap: cannot download src.zip: %s', e)
            return None
        else:
            return resp

    def unpack_src(self, zipdata):
        if self.src.exists():
            Logger.info('bootstrap: removing existing src directory')
            self.src.remove()
        Logger.info('bootstrap: extracting src.zip to %s', self.root)
        buf = BytesIO(zipdata)
        zipf = ZipFile(buf, 'r')
        zipf.extractall(str(self.root))
        assert self.src.exists()

    def load(self):
        # Dynamically set the root of the app to "src". This includes:
        #
        #   1. put src and src/libs in sys.path
        #
        #   2. add src to resource path, so that we can load assets by using
        #      e.g. resource_find('data/icon.png') and find it in
        #      src/data/icon.png
        #
        Logger.info('bootstrap: loading %s', self.src)
        libs = self.src.join('libs')
        garden = libs.join('garden')
        sys.path.append(str(self.src))           # 1
        sys.path.append(str(libs))               # 1
        resource_add_path(str(self.src))         # 2



kv = """
BoxLayout:
    message: ""
    orientation: 'vertical'

    TextInput:
        text: root.message
        readonly: True
        is_focusable: False

    BoxLayout:
        size_hint: 1, None
        height: "50dp"

        Label:
            id: status
            text: "Status..."

        Button:
            text: "Controlla..."
            on_release: app.check_server()

    BoxLayout:
        size_hint: 1, None
        height: "50dp"

        Button:
            text: "Impostazioni"
            on_release: app.open_settings()

        Button:
            text: "Esci"
            on_release: app.stop()
"""

MESSAGE = """\
Impossibile contattare il sync server.
Controllare che:

  1. Il sync server sia in esecuzione

  2. L'indirizzo del server nelle impostazioni sia corretto

  3. Il cellulare sia collegato alla rete WIFI corretta.

Una volta impostato l'indirizzo corretto, premere "Controlla..." per \
controllare il collegamento con il server. Infine, riavviare il programma.
"""

class BootstrapApp(App):

    def __init__(self, rootdir, **kwargs):
        self.rootdir = rootdir
        super(BootstrapApp, self).__init__(**kwargs)

    def get_application_config(self):
        ini = self.rootdir.join('mcont.ini')
        Logger.info('bootstrap: config file is %s', ini)
        return str(ini)

    def build(self):
        root = Builder.load_string(kv)
        root.message = MESSAGE
        self.root = root
        self.set_status("offline")
        return root

    def build_config(self, config):
        config.setdefaults('server', {
            'host': DEFAULT_HOST,
            'port': DEFAULT_PORT
        })

    def build_settings(self, settings):
        filename = resource_find('data/settings_bootstrap.json')
        settings.add_json_panel('App', self.config, filename=filename)

    def set_status(self, status):
        assert status in ('offline', 'checking', 'online')
        lbl = self.root.ids.status
        if status == 'offline':
            lbl.text = 'Server offline'
            lbl.color = (0.8, 0, 0, 1) # red
        elif status == 'checking':
            lbl.text = 'Collegamento...'
            lbl.color = (0.8, 0.8, 0, 1) # yellow
        else:
            lbl.text = 'Server online'
            lbl.color = (0, 0.8, 0, 1) # green

    def check_server(self):
        host = self.config.get('server', 'host')
        port = self.config.get('server', 'port')
        url = SRC_URL.format(host=host, port=port)
        self.set_status('checking')
        def do(dt):
            try:
                resp = requests.head(url, timeout=TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as e:
                Logger.error('bootstrap: server still offline: %s', e)
                time.sleep(0.5) # make sure that the checking text is visible
                                # to the user
                self.set_status('offline')
            else:
                self.set_status('online')
        #
        Clock.schedule_once(do, 0)
