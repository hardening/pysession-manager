import pbRPC_pb2
import ICP_pb2
import SocketServer
import os, os.path
import time
import struct
import sys
import json
import content_provider

pipeDir = os.path.join("/tmp", ".pipe")

KNOWN_USERS = {
    'local': {
        'david': 'david'
    },    
}

ICP_METHODS_TO_BIND = ("IsChannelAllowed", "Ping", "GetUserSession",
    "DisconnectUserSession", "LogOffUserSession",
    "FdsApiVirtualChannelOpen", "LogonUser"
)

def buildIcpMethodDescriptor():
    ret = {}
    for messageIdName in ICP_METHODS_TO_BIND:
        messageId = getattr(ICP_pb2, messageIdName, None)
        if messageId is None:
            print "unable to retrieve %s" % messageIdName
            continue
        
        reqCtor = getattr(ICP_pb2, messageIdName + "Request", None)
        if reqCtor is None:
            print "unable to retrieve %sRequest" % messageIdName
            continue
        ret[messageId] = (messageIdName, reqCtor)
    return ret
        



class PbRpcHandler(SocketServer.BaseRequestHandler):
    '''
        @summary: a base class to handle the protobuf RPC protocol that is spoken
                  between FreeRDS and the sessionManager
    '''

    def answer404(self, pbRpc):
        pbRpc.status = pbRPC_pb2.RPCBase.NOTFOUND
        pbRpc.isResponse = True
        pbRpc.payload = None
        response = pbRpc.SerializeToString()
        self.request.send( struct.pack("!i", len(response)) )                  
        self.request.send( response )
        return 404            
    
    def treat_request(self, pbRpc):
        cbInfos = self.methodMapper.get(pbRpc.msgType, None)         
        if cbInfos is None:
            print "unknown method with id=%s" % pbRpc.msgType
            return self.answer404(pbRpc)                        
        
        (methodName, ctor) = cbInfos
        toCall = getattr(self, methodName, None)
        if not callable(toCall):
            print "unknown method with id=%s" % pbRpc.msgType
            return self.answer404(pbRpc)                        
                     
        obj = ctor()
        obj.ParseFromString(pbRpc.payload)

        ret = toCall(obj)
        if ret:
            pbRpc.status = pbRPC_pb2.RPCBase.SUCCESS
            pbRpc.isResponse = True
            pbRpc.payload = ret.SerializeToString()
            response = pbRpc.SerializeToString()
            self.request.send( struct.pack("!i", len(response)) )                  
            self.request.send( response )
        return 200
        
    def handle(self):
        while True:
            lenBytes = self.request.recv(4)
            if not len(lenBytes):
                break            
            msgLen = struct.unpack("!i", lenBytes)[0]
            
            msg = self.request.recv(msgLen)
            baseRpc = pbRPC_pb2.RPCBase()
            baseRpc.ParseFromString(msg)
            
            if baseRpc.isResponse:
                self.treat_response(baseRpc)
            else:
                self.treat_request(baseRpc)
                

class IcpHandler(PbRpcHandler):
    '''
        @summary: the ICP part of the SessionManager
    '''
    globalId = 0
        
    def __init__(self, *params, **kwparams):
        self.methodMapper = buildIcpMethodDescriptor()
        PbRpcHandler.__init__(self, *params, **kwparams)
                
        
    def GetUserSession(self, getUserReq):
        print "getUserSession(%s@%s)" % (getUserReq.username, getUserReq.domainname)
        ret = ICP_pb2.GetUserSessionResponse()
        ret.SessionID = self.globalId
        #self.globalId += 1
        ret.ServiceEndpoint = "\\\\.\\pipe\\FreeRDS_%d_greeter" % ret.SessionID
        
        pipeName = '%s/FreeRDS_%d_greeter' % (pipeDir, ret.SessionID)        
        if False and os.fork() == 0:
            prog = "/home/david/dev/git/qfreerdp_platform/chart.sh"       
            args = [prog, pipeName, '-platform', 'freerds:width=%d:height=%d' % (1024, 768)]
            os.execl(prog, *args)            
        
        waitTime = 0.0
        while waitTime < 10:
            if not os.path.exists(pipeName):
                time.sleep(0.1)
            waitTime += 0.1
        
        if not os.path.exists(pipeName):
            return None
        return ret
    
    def IsChannelAllowed(self, msg):
        print "IsChannelAllowed(%s)" % msg.ChannelName
        ret = ICP_pb2.IsChannelAllowedResponse()
        ret.ChannelAllowed = True
        return ret
    
    def LogonUser(self, msg):
        print "LogonUser(session=%s user=%s domain=%s)" % (msg.SessionId, msg.Username, msg.Domain)
        ret = ICP_pb2.LogonUserResponse()
        ret.AuthStatus = 1;

        domainUsers = KNOWN_USERS.get(msg.Domain, None)
        if domainUsers:
            localPassword = domainUsers.get(msg.Username, None)
            if localPassword == msg.Password:
                ret.AuthStatus = 0;

        sessionId = msg.SessionId
        pipeName = None
        if ret.AuthStatus != 0:
            (sessionId, pipeName) = self.server.retrieveGreeter(msg.Username, msg.Domain, sessionId)
        else:
            pipeName = self.server.retrieveDesktop(sessionId)
            
        ret.SessionId = sessionId
        ret.ServiceEndpoint = "\\\\.\\pipe\\%s" % pipeName
        return ret
      
    def DisconnectUserSession(self, msg):
        print "DisconnectUserSession(%s)" % msg.SessionID
        ret = ICP_pb2.DisconnectUserSessionResponse()
        ret.disconnected = True
        return ret
    

class FreeRdsSession(object):
    def __init__(self, sessionId, user, domain):
        self.id = sessionId
        self.login = user
        self.domain = domain
        self.authenticated = False
        self.greeter_pipe = None
        self.greeter_pid = -1
        self.desktop_pipe = None
        self.desktop_pid = -1
        

class SessionManagerServer(SocketServer.ThreadingUnixStreamServer):
    '''
        @summary: 
    '''
    
    def __init__(self, config):
        '''
            @param config: the global configuration 
        '''
        self.config = config
        self.sessions = {}
        if not os.path.exists(config.global_pipesDirectory):
            os.makedirs(config.global_pipesDirectory)
            
        server_address = os.path.join(config.global_pipesDirectory, config.global_listeningPipe)
        if os.path.exists(server_address):
            os.remove(server_address)
                
        SocketServer.ThreadingUnixStreamServer.__init__(self, server_address, IcpHandler)
        
    def launchByTemplate(self, template, sessionId, appName, appPath):
        if template == "qt":
            providerCtor = content_provider.QtContentProvider
        elif template == "weston":
            providerCtor = content_provider.WestonContentProvider
        else:
            print "%s not handled yet using generic"
            providerCtor = content_provider.SessionManagerContentProvider
        
        provider = providerCtor(appName, appPath, [])
        return provider.launch(self.config, sessionId, [])            
        
        
    def retrieveGreeter(self, username, domain, sessionId):
        session = None
        if sessionId: # a SessionId set to 0 means that the session does not exist yet
            session = self.sessions.get(sessionId, None)
        else:
            sessionId = 1
        
        if not session: 
            # scan existing sessions
            for s in self.sessions.values():
                if (s.login == username) and (s.domain == domain):
                    sessionId = s.id
                    session = s
                    break
                    
        if not session:
            # allocate a new one
            while self.sessions.get(sessionId, None):
                sessionId += 1
                
            session = FreeRdsSession(sessionId, username, domain)
            self.sessions[sessionId] = session
        
        if not session.greeter_pipe:
            ret = self.launchByTemplate(self.config.greeter_template, sessionId, 
                                        "greeter", self.config.greeter_path)
            if not ret:
                print "Fail to launch a greeter"
            (session.greeter_pid, session.greeter_pipe) = ret 
        return (sessionId, session.greeter_pipe)
            
    def retrieveDesktop(self, sessionId):
        session = self.sessions.get(sessionId, None)
        if not session:
            print "Fatal error, session not found"
            
        if not session.desktop_pipe:
            ret = self.launchByTemplate(self.config.desktop_template, sessionId, 
                                        "desktop", self.config.desktop_path)
            if not ret:
                print "Fail to launch a desktop"
                return None
            (session.desktop_pid, session.desktop_pipe) = ret 
        return session.desktop_pipe
        
        

DEFAULT_CONFIG = {
    'global': {
        'pipesDirectory': '/tmp/.pipe',
        'listeningPipe': 'FreeRDS_SessionManager',
        'ld_library_path': [],
        'pipeTimeout': 10,
    },
                  
    'qt': {
        'pluginsPath': None,
        'variableName': 'FREERDS_PIPE_PATH',
        'initialGeometry': '800x600',
    },
                  
    'weston': {
        'initialGeometry': '1024x768',
    },
    
    'greeter': {
        'template': 'qt',
        'path': None,
    },
    
    'desktop': {
        'template': 'weston',
        'path': None
    }
}

class SessionManagerConfig(object):
    def __init__(self):
        self.global_pipesDirectory = None
        self.global_listeningPipe = None
        self.ld_library_path = None
        self.pipeTimeout = None
        
        self.qt_pluginsPath = None
        self.qt_variableName = None
        self.qt_initialGeometry = None
        
        self.weston_initialGeometry = None
        
        self.greeter_template = None
        self.greeter_path = None

        self.desktop_template = None
        self.desktop_path = None
        

    def loadFromFile(self, fname):
        ''' load JSON configuration from frm the given filename
            @param fname: the name of the configuration file 
        '''        
        config = json.load(open(fname, "r"))
        
        for topK, defaultTopValues in DEFAULT_CONFIG.items():
            localConfig = config.get(topK, {})
                
            for k, defaultV in defaultTopValues.items():
                v = localConfig.get(k, defaultV)            
                setattr(self, topK + '_' + k, v)        
            
              
if __name__ == "__main__":
    mainConfig = SessionManagerConfig()
    mainConfig.loadFromFile(sys.argv[1])
        
    server = SessionManagerServer(mainConfig)
    server.serve_forever()
    
