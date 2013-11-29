import pbRPC_pb2
import ICP_pb2
import ICPS_pb2
import SocketServer
import os, os.path
import time
import struct
import sys
import json
import content_provider


ICP_METHODS_TO_BIND = ("IsChannelAllowed", "Ping", "DisconnectUserSession", 
    "LogOffUserSession", "FdsApiVirtualChannelOpen", "LogonUser",
)

ICPS_METHODS_TO_BIND = ("AuthenticateUser", 'EndSession',)

def buildMethodDescriptor(module, methods):
    ret = {}
    for messageIdName in methods:
        messageId = getattr(module, messageIdName, None)
        if messageId is None:
            print "unable to retrieve %s" % messageIdName
            continue
        
        reqCtor = getattr(module, messageIdName + "Request", None)
        if reqCtor is None:
            print "unable to retrieve %sRequest" % messageIdName
            continue
        ret[messageId] = (messageIdName, reqCtor)
    return ret
        
class PbRpcResponseHandler(object):
    '''
        @summary: base class for a pbRpc transaction context
    '''
    def __init__(self, reqHandler, responseCtor):
        self.reqHandler = reqHandler
        self.ctor = responseCtor
        
    def handle(self, status, payload):
        response = None
        if payload:
            response = self.ctor()
            response.ParseFromString(payload)
        self.onResponse(status, response)
        
    def onResponse(self, status, response):
        pass


class PbRpcHandler(SocketServer.BaseRequestHandler):
    '''
        @summary: a base class to handle the protobuf RPC protocol that is spoken
                  between FreeRDS and the sessionManager
    '''

    def __init__(self, *args, **kwargs):
        self.requestsToInitiate = []
        self.requestsInProgress = {}
        self.tagCounter = 1
        SocketServer.BaseRequestHandler.__init__(self, *args, **kwargs)
            
    def scheduleRequest(self, reqType, payload, handler):
        self.requestsToInitiate.append( (reqType, payload, handler) )
    
    def answer404(self, pbRpc):
        ''' answers a "404 not found" like message in the pcbRpc terminology
            @param pbRpc: the incoming request that will be used to forge an answer
            @return: 404 as error code 
        '''
        pbRpc.status = pbRPC_pb2.RPCBase.NOTFOUND
        pbRpc.isResponse = True
        pbRpc.payload = ''
        response = pbRpc.SerializeToString()
        self.request.send( struct.pack("!i", len(response)) )                  
        self.request.send( response )
        return 404            
    
    def treat_request(self, pbRpc):
        cbInfos = self.methodMapper.get(pbRpc.msgType, None)         
        if cbInfos is None:
            print "PbRpcHandler(): unknown method with id=%s" % pbRpc.msgType
            return self.answer404(pbRpc)                        
        
        (methodName, ctor) = cbInfos
        toCall = getattr(self, methodName, None)
        if not callable(toCall):
            print "PbRpcHandler(): unknown method with id=%s" % pbRpc.msgType
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

        for (icpType, payload, cb) in self.requestsToInitiate:
            self.tagCounter += 1
            tag = self.tagCounter
                        
            req = pbRPC_pb2.RPCBase()
            req.msgType = icpType
            req.tag = tag
            req.isResponse = False
            req.status = pbRPC_pb2.RPCBase.SUCCESS
            req.payload = payload

            self.requestsInProgress[tag] = cb
            
            requestContent = req.SerializeToString()
            self.request.send( struct.pack("!i", len(requestContent)) )                  
            self.request.send( requestContent )
        
        self.requestsToInitiate = []                    
        return 200
        
    def treat_response(self, msg):
        reqContext = self.requestsInProgress.get(msg.tag, None)
        if not reqContext:
            print "treat_response(): receiving a response(tag=%d type=%d) but no request is registered here" % (msg.tag, msg.msgType)
            return
                
        del self.requestsInProgress[msg.tag]
        reqContext.handle(msg.status, msg.payload)
        
                
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
                

class SwitchPipeHandler(PbRpcResponseHandler):
    '''
        @summary: a context object to handle a switchPipe ICP transaction
    '''
    
    def __init__(self, reqHandler, session, pipeName):
        PbRpcResponseHandler.__init__(self, reqHandler, ICP_pb2.SwitchToResponse)
    
    def onResponse(self, status, response):
        if response:
            print "switchPipe result: %d" % response.success
        else:
            print "error treating switchPipe()"
        

class LogoffHandler(PbRpcResponseHandler):
    '''
        @summary: a context object to handle a LogOffUser transaction
    '''
    
    def __init__(self, reqHandler, session):
        PbRpcResponseHandler.__init__(self, reqHandler, ICP_pb2.LogOffUserSessionResponse)
    
    def onResponse(self, status, response):
        if response:
            print "LogoffHandler result: %s" % response.loggedoff
        else:
            print "error treating LogoffHandler()"


class IcpHandler(PbRpcHandler):
    '''
        @summary: a handler that will take care of ICP messages
    '''
        
    def __init__(self, *params, **kwparams):
        self.methodMapper = buildMethodDescriptor(ICP_pb2, ICP_METHODS_TO_BIND)
        self.methodMapper.update(buildMethodDescriptor(ICPS_pb2, ICPS_METHODS_TO_BIND))
        PbRpcHandler.__init__(self, *params, **kwparams)
                    
    def IsChannelAllowed(self, msg):
        print "IsChannelAllowed(%s)" % msg.ChannelName
        ret = ICP_pb2.IsChannelAllowedResponse()
        ret.ChannelAllowed = True
        return ret
    
    def LogonUser(self, msg):
        print "LogonUser(connectionId=%s user=%s domain=%s)" % (msg.ConnectionId, msg.Username, msg.Domain)
        ret = ICP_pb2.LogonUserResponse()

        session = self.server.logonUser(msg.ConnectionId, msg.Username, msg.Password, msg.Domain)
        pipeName = None
        if not session.isAuthenticated():                        
            pipeName = self.server.retrieveGreeter(session)
        else:
            pipeName = self.server.retrieveDesktop(session)
            
        ret.ServiceEndpoint = "\\\\.\\pipe\\%s" % pipeName
        return ret

    def DisconnectUserSession(self, msg):
        print "DisconnectUserSession(%s)" % msg.ConnectionId
        ret = ICP_pb2.DisconnectUserSessionResponse()
        ret.disconnected = True
        return ret
    
    #
    #    ICPS API
    #
     
    def AuthenticateUser(self, msg):        
        user = msg.username
        password = msg.password
        domain = msg.domain
        print "Authenticate(sessionId=%s user=%s password=%s domain=%s)" % (msg.sessionId, user, password, domain)
        
        ret = ICPS_pb2.AuthenticateUserResponse()

        session = self.server.retrieveSession(msg.sessionId)
        if session is None:
            print "Authenticate(): no such session %s" % msg.sessionId
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_INVALID_PARAMETER
            return ret         
        
        # uncomment this line if you would like to see the nice effect when authenticating
        #time.sleep(1)  
        if self.server.authenticate(user, password, domain):
            session.login = user
            session.domain = domain
            session.authenticated = True
            
            pipeName = self.server.retrieveDesktop(session)
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_SUCCESSFULL
            ret.serviceEndpoint = "\\\\.\\pipe\\%s" % pipeName
            
            switchHandler = SwitchPipeHandler(self, session, pipeName)
            switchReq = ICP_pb2.SwitchToRequest()
            switchReq.connectionId = session.connectionId
            switchReq.serviceEndpoint = ret.serviceEndpoint
            self.scheduleRequest(ICP_pb2.SwitchTo, switchReq.SerializeToString(), switchHandler)            
        else:
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_BAD_CREDENTIAL
            ret.serviceEndpoint = ""            
        return ret
      
    def EndSession(self, msg):
        print "EndSession(%s)" % msg.sessionId
        session = self.server.retrieveSession(msg.sessionId)
        
        ret = ICPS_pb2.EndSessionResponse()
        if session is None or session.connectionId is None:
            ret.success = False
            return ret
        
        ret.success = True        
        disconnectHandler = LogoffHandler(self, session)
        logoffReq = ICP_pb2.LogOffUserSessionRequest()
        logoffReq.ConnectionId = session.connectionId
        self.scheduleRequest(ICP_pb2.LogOffUserSession, logoffReq.SerializeToString(), 
                             disconnectHandler)            
        return ret



class FreeRdsSession(object):
    def __init__(self, connectionId, user, domain):
        self.sessionId = 0
        self.connectionId = connectionId
        self.login = user
        self.domain = domain
        self.authenticated = False
        self.greeter = None
        self.desktop = None
        
    def getId(self):
        return self.sessionId
    def isAuthenticated(self):
        return self.authenticated

KNOWN_USERS = {
    'local': {
        'david': 'david'
    },    
}

class SessionManagerServer(SocketServer.UnixStreamServer):
    '''
        @summary: the main ICP server listening for FreeRds connections 
    '''
    
    def __init__(self, config):
        '''
            @param config: the global configuration 
        '''
        self.config = config
        self.sessions = {}
        self.sessionCounter = 1
        if not os.path.exists(config.global_pipesDirectory):
            os.makedirs(config.global_pipesDirectory)
            
        server_address = os.path.join(config.global_pipesDirectory, config.global_listeningPipe)
        if os.path.exists(server_address):
            os.remove(server_address)
              
        self.processReaper = content_provider.ContentProviderReaper()
        self.processReaper.start()
        
        SocketServer.UnixStreamServer.__init__(self, server_address, IcpHandler)

    def logonUser(self, connectionId, username, password, domain):
        authRes = self.authenticate(username, password, domain)
        
        if authRes:
            for session in self.sessions.values():
                if (session.login == username) and (session.domain == domain):
                    session.authenticated = True
                    session.connectionId = connectionId
                    return session
                        
        session = FreeRdsSession(connectionId, username, domain)
        self.sessionCounter += 1
        sid = self.sessionCounter
        session.sessionId = sid
        self.sessions[sid] = session            
        return session
        
    def authenticate(self, username, password, domain):
        domainUsers = KNOWN_USERS.get(domain, None)
        if not domainUsers:
            return False            
        
        localPassword = domainUsers.get(username, None)
        return localPassword == password

    def retrieveSession(self, sessionId):
        return self.sessions.get(sessionId, None)
        
    
    def launchByTemplate(self, template, sessionId, appName, appPath):
        if template == "qt":
            providerCtor = content_provider.QtContentProvider
        elif template == "weston":
            providerCtor = content_provider.WestonContentProvider
        else:
            print "%s not handled yet, using generic"
            providerCtor = content_provider.SessionManagerContentProvider
        
        provider = providerCtor(appName, appPath, [])
        if provider.launch(self.config, self.processReaper, sessionId, []) is None:
            return None
        return provider           
        
        
    def retrieveGreeter(self, session):
        if not session.greeter or not session.greeter.isAlive():
            session.greeter = self.launchByTemplate(self.config.greeter_template, session, 
                                        "greeter", self.config.greeter_path)
            if not session.greeter:
                print "Fail to launch a greeter"
                return None
            
        return session.greeter.pipeName
            
    def retrieveDesktop(self, session):
        session = self.sessions.get(session.getId(), None)
        if not session:
            print "Fatal error, session not found"
            
        if not session.desktop or not session.desktop.isAlive():
            session.desktop = self.launchByTemplate(self.config.desktop_template, session, 
                                        "desktop", self.config.desktop_path)
            if not session.desktop:
                print "Fail to launch a desktop"
                return None
 
        return session.desktop.pipeName
        
        

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
    
