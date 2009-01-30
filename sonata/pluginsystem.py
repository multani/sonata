
import os, re, StringIO
import ConfigParser, pkgutil

import sonata.plugins

def find_plugin_dirs():
    return [os.path.expanduser('~/.sonata/plugins'),
        '/usr/local/lib/sonata/plugins']

# add dirs from sys.path:
sonata.plugins.__path__ = pkgutil.extend_path(sonata.plugins.__path__,
                          sonata.plugins.__name__)
# add dirs specific to sonata:
sonata.plugins.__path__ = find_plugin_dirs() + sonata.plugins.__path__

class PluginSystem(object):
    def __init__(self):
        self.plugin_infos = []
        self.loaded_plugins = {}

    def get(self, capability):
        ret = []
        for path, name, info in self.plugin_infos:
            if info.has_option('capabilities', capability):
                features = info.get('capabilities', capability)
                ret += self.get_features(path, name, features)
        return ret

    def get_features(self, path, name, features):
        plugin = self.get_plugin(path, name)
        if not plugin:
            return []

        try:
            return [getattr(plugin, f)
                for f in features.split(', ')]
        except KeyboardInterrupt:
            raise
        except Exception:
            print "Failed to access features in plugin %s." % name
            return []

    def get_plugin(self, path, name):
        if name not in self.loaded_plugins:
            try:
                self.load_plugin(path, name)
            except Exception:
                print "Failed to load plugin %s." % name
                return None
        return self.loaded_plugins[name]

    def find_plugins(self):
        for path in sonata.plugins.__path__:
            if not os.path.isdir(path):
                continue
            for entry in os.listdir(path):
                if entry.startswith('_'):
                    continue # __init__.py etc.
                if entry.endswith('.py'):
                    try:
                        self.load_info(path, entry[:-3])
                    except Exception:
                        print "Failed to load info:",
                        print os.path.join(path, entry)

    def load_info(self, path, name):
        f = open(os.path.join(path, name+".py"), "rt")
        text = f.read()
        f.close()

        pat = r'^### BEGIN PLUGIN INFO.*((\n#.*)*)\n### END PLUGIN INFO'
        infotext = re.search(pat, text, re.MULTILINE).group(1)
        uncommented = '\n'.join(line[1:].strip()
                    for line in infotext.split('\n'))
        info = ConfigParser.SafeConfigParser()
        info.readfp(StringIO.StringIO(uncommented))

        # XXX add only newest version of each name
        self.plugin_infos.append((path, name, info))
        if not info.options('capabilities'):
            print "Warning: No capabilities in plugin %s." % name

    def load_plugin(self, path, name):
        # XXX load from a .py file - no .pyc etc.
        plugin = self.import_plugin(name)
        self.loaded_plugins[name] = plugin

    def import_plugin(self, name):
        __import__('sonata.plugins', {}, {}, [name], 0)
        plugin = getattr(sonata.plugins, name)
        return plugin

pluginsystem = PluginSystem()
