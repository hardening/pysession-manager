import os.path
import sys, time
import content_provider
import signal
import dbus, dbus.service
import random, string
import types
from dbus.mainloop.glib import DBusGMainLoop
import wtsapi
import logging
import logging.config

sys.path.append('gen-py.twisted')

from twisted.internet import reactor, ssl
from icp_server import IcpFactory
import thrift_server
from OpenSSL import SSL


DEFAULT_CONFIG = {
    'globalConfig': {
        'pipesDirectory': '/tmp/.pipe',
        'ld_library_path': [],
        'pipeTimeout': 10,
        'xdg_runtime_schema': '/run/user/${runAsUserId}',
        'user_default_path': ['/usr/local/sbin', '/usr/local/bin', '/usr/sbin', 
                              '/usr/bin', '/sbin', '/bin'],
        'tokensTemplate': '/tmp/freerds.session.%s',
    },

    'icp': {
        'listeningPipe': 'FreeRDS_SessionManager',
        'mode': 0666,
    },
    
    'thrift': {
        'certPath': 'server.crt',
        'keyPath': 'server.key',
        'listeningIp': '127.0.0.1',
        'listeningPort': 9091,
    },
                  
    'freerds': {
        "forceWeakRdpKey": False,
        "showDebugInfo": False,
        "disableGraphicsPipeline": False,
        "disableGraphicsPipelineH264": False,
    },
                  
    'qt': {
        'pluginsPath': None,
        'variableName': 'FREERDS_PIPE_PATH',
        'initialGeometry': '800x600',
    },
                  
    'weston': {
        'initialGeometry': '1024x768',
        'serverPath': None,
    },

    'x11': {
        'initialGeometry': '1024x768',
        'depth': '24',
        'serverPath': None,
        'wmPath': None,
    },
    
    'greeter': {
        'template': 'qt',
        'path': None,
        'user': None,
    },
    
    'desktop': {
        'template': 'weston',
        'path': None,
        'user': '${user}',
    }
}

def updateConfigMap(configInFile, config):
    for k, v in config.items():
        if not configInFile.has_key(k): 
            continue
        
        if type(v) in [types.IntType, types.TupleType, types.ListType] + list(types.StringTypes):
            config[k] = configInFile[k]
        else:
            v.update(configInFile[k])
                

tokenChars = string.ascii_letters + string.digits

logger = logging.getLogger("session")

class FreeRdsSession(object):
    """
        @summary: 
    """
    
    def __init__(self, connectionId, user, domain):
        self.sessionId = 0
        self.token = ''.join(random.sample(tokenChars, 20))
        self.tokenFile = None
        self.connectionId = connectionId
        self.login = user
        self.domain = domain
        self.hostname = None
        self.authenticated = False
        self.greeter = None
        self.desktop = None
        self.connectTime = time.time()
        self.logonTime = 0
        self.disconnectTime = time.time()
        self.state = wtsapi.WTSInit
        
    def getId(self):
        return self.sessionId
    
    def isAuthenticated(self):
        return self.authenticated

    def close(self):
        if self.greeter:
            logger.info("%s: killing greeter process" % self.sessionId)
            self.greeter.close()
        
        if self.desktop:
            logger.info("%s: killing desktop process" % self.sessionId)
            self.desktop.close()



class SessionManagerServer(object):
    '''
        @summary: the main ICP server listening for FreeRds connections 
    '''
    
    def __init__(self, config, canImpersonnate):
        '''
            @param config: the global configuration 
        '''
        self.config = config
        self.canImpersonnate = canImpersonnate
        self.sessions = {}
        self.sessionCounter = 1
              
        self.processReaper = content_provider.ContentProviderReaper()
        self.processReaper.start()
        self.icpFactory = None
        self.system_dbus = None
                        
    def logonUser(self, connectionId, username, password, domain, hostname):
        authRes = self.authenticate(username, password, domain)
        
        if authRes:
            for session in self.sessions.values():
                if session.login != username:
                    continue
                if session.domain != domain:
                    continue
                if hostname and session.hostname != hostname:
                    continue
                
                session.authenticated = True
                session.connectionId = connectionId
                session.state = wtsapi.WTSActive
                logger.info("logonUser(login=%s, domain=%s): reusing session %d" % (username, domain, session.getId()))
                return session
                        
        session = FreeRdsSession(connectionId, username, domain)
        self.sessionCounter += 1
        sid = self.sessionCounter
        session.sessionId = sid
        session.state = authRes and wtsapi.WTSActive or wtsapi.WTSConnected
        session.authenticated = authRes
        session.tokenFile = self.config['globalConfig']["tokensTemplate"] % session.getId() 
        self.sessions[sid] = session
        
        # write token file for channel authentication
        open(session.tokenFile, "w").write(session.token)
        
        logger.info("logonUser(login=%s, domain=%s): returning session %d" % (username, domain, sid))         
        return session
    
    
    def authenticate(self, username, password, domain):
        return self.config['globalConfig']['authMethod'].authenticate(username, domain, password)

    def retrieveSession(self, sessionId):
        return self.sessions.get(sessionId, None)

    def retrieveSessionByConnectionId(self, connectionId):
        for s in self.sessions.values():
            if s.connectionId == connectionId:
                return s
            
        return None
            
    def launchByTemplate(self, template, session, appName, appPath, runAs = None):
        if template == "qt":
            providerCtor = content_provider.QtContentProvider
        elif template == "weston":
            providerCtor = content_provider.WestonContentProvider
        elif template == "static":
            providerCtor = content_provider.StaticContentProvider
        elif template == "x11":
            providerCtor = content_provider.X11ContentProvider
        else:
            logger.error("%s not handled yet, using generic" % template)
            providerCtor = content_provider.ContentProvider
        
        peerCred = self.icpFactory.freeRdsInstance.peerCredentials 
        provider = providerCtor(appName, appPath, [])
        if provider.launch(self.config, self.processReaper, session, [], runAs, peerCred) is None:
            return None
        return provider           
        
        
    def retrieveGreeter(self, session):
        greeterConfig = self.config['greeter']
        if not session.greeter or not session.greeter.isAlive():
            session.greeter = self.launchByTemplate(greeterConfig['template'], 
                            session, "greeter", 
                            greeterConfig['path'], greeterConfig['user']
            )
            if not session.greeter:
                logger.error("retrieveGreeter(): fail to launch a greeter for session %s" % session.getId())
                return None
        
        if not session.greeter.initProvider(self.config):
            logger.error("retrieveGreeter(): unable to setup the provider for session %s" % session.getId())
            return None
              
        return session.greeter.pipeName
 
            
    def retrieveDesktop(self, session):
        desktopConfig = self.config['desktop']

        session = self.sessions.get(session.getId(), None)
        if not session:
            logger.error("retrieveDesktop(): session %s not found" % session.getId())
            
        if not session.desktop or not session.desktop.isAlive():
            session.desktop = self.launchByTemplate(desktopConfig['template'], 
                            session, "desktop", 
                            desktopConfig['path'], desktopConfig['user']
            )
            if not session.desktop:
                logger.error("retrieveDesktop(): fail to launch a desktop for session %s" % session.getId()) 
                return None

        if not session.desktop.initProvider(self.config):
            logger.error("retrieveDesktop(): unable to setup the provider for session %s" % session.getId())
            return None
 
        return session.desktop.pipeName

    def removeSession(self, session):
        if session in self.sessions.values():
            del self.sessions[session.sessionId]
  
class SessionNotification(dbus.service.Object):
    
    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, "/freerds/SessionManager/session/notification")
        
    @dbus.service.signal("freerds.SessionManager.session.notification", "uu")
    def SessionNotification(self, reason, sessionId):
        pass

if __name__ == "__main__":
    logging.config.fileConfig("sessionManager.logconfig")
    canImpersonnate = True
    if os.getuid() != 0:
        logger.warn("not running as root, let's hope we will not have to impersonnate")
        canImpersonnate = False
    
    # TODO: treat number of arguments
    mainConfig = DEFAULT_CONFIG.copy()
    
    configInFile = {}
    execfile(sys.argv[1], {}, configInFile)
    updateConfigMap(configInFile, mainConfig)
    
    
    globalConfig = mainConfig['globalConfig']
    icpConfig = mainConfig['icp']
    pipesDir = globalConfig['pipesDirectory']
    if not os.path.exists(pipesDir):
        os.makedirs(pipesDir, mode=0777)
            
    pipePath = os.path.join(pipesDir, icpConfig['listeningPipe'])
    if os.path.exists(pipePath):
        os.remove(pipePath)

    core = SessionManagerServer(mainConfig, canImpersonnate)
    core.icpFactory = IcpFactory(core)
    thriftFactory = thrift_server.FdsFactory(core)
    
    icpServer = reactor.listenUNIX(pipePath, core.icpFactory, icpConfig['mode'])
    
    thriftConfig = mainConfig['thrift']
    sslFactory = ssl.DefaultOpenSSLContextFactory(thriftConfig['keyPath'], 
                                                  thriftConfig['certPath'], 
                                                  sslmethod=SSL.TLSv1_METHOD
    )
    thriftServer = reactor.listenSSL(thriftConfig['listeningPort'], thriftFactory, sslFactory, interface=thriftConfig["listeningIp"])
    
    loop = DBusGMainLoop(set_as_default=True)
    core.system_dbus = dbus.SystemBus(mainloop=loop)
    err = core.system_dbus.request_name("freerds.SessionManager.session.notification", dbus.bus.NAME_FLAG_REPLACE_EXISTING);
    if err != dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER:
        logger.info("unable to acquire the notification name (err=%d)" % err)
        #sys.exit(1)
    else:
        core.sessionNotification = SessionNotification(core.system_dbus)
    
    
    def sigIntCb(signum, sf):
        print "keyboard interrupt"
        reactor.stop()
    signal.signal(signal.SIGINT, sigIntCb)
    reactor.run()

