import pbRPC_pb2
import ICP_pb2
import ICPS_pb2
import socket
import struct
from twisted.internet.protocol import Protocol, ServerFactory
import wtsapi
import logging


ICP_METHODS_TO_BIND = ("IsChannelAllowed", "Ping", "DisconnectUserSession", 
    "LogoffUserSession", "FdsApiVirtualChannelOpen", "LogonUser",
    "RemoteControlEnded", "PropertyString", "PropertyNumber", "PropertyBool"
)

ICPS_METHODS_TO_BIND = ("AuthenticateUser", 'EndSession', 'VersionInfo')

logger = logging.getLogger("icp")

def buildMethodDescriptor(module, methods):
    ret = {}
    for messageIdName in methods:
        messageId = getattr(module, messageIdName, None)
        if messageId is None:
            logger.error("unable to retrieve %s" % messageIdName)
            continue
        
        reqCtor = getattr(module, messageIdName + "Request", None)
        if reqCtor is None:
            logger.error("unable to retrieve %sRequest" % messageIdName)
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


class SwitchPipeHandler(PbRpcResponseHandler):
    '''
        @summary: a context object to handle a switchPipe ICP transaction
    '''
    
    def __init__(self, reqHandler, session, pipeName):
        PbRpcResponseHandler.__init__(self, reqHandler, ICP_pb2.SwitchToResponse)
    
    def onResponse(self, status, response):
        if response:
            logger.error("switchPipe result: %d" % response.success)
        else:
            logger.error("error treating switchPipe()")
        

class LogoffHandler(PbRpcResponseHandler):
    '''
        @summary: a context object to handle a LogOffUser transaction
    '''
    
    def __init__(self, reqHandler, session):
        PbRpcResponseHandler.__init__(self, reqHandler, ICP_pb2.LogoffUserSessionResponse)
    
    def onResponse(self, status, response):
        if response:
            logger.error("LogoffHandler result: %s" % response.loggedoff)
        else:
            logger.error("error treating LogoffHandler()")


def hexadump(s):
    ret = ''
    hexa = s.encode('hex')
    while len(hexa):
        ret += hexa[0:2] + " "
        hexa = hexa[2:]
    return ret


VERSION_INFO_MSGTYPE = 4294967295


class PeerCredentials(object):
    ''' identity of the socket peer '''
    def __init__(self, uid, gid, pid = None):
        self.uid = uid
        self.gid = gid
        self.pid = pid
        
def getPeerCredential(sock):
    SO_PEERCRED = 17 # Pulled from /usr/include/asm-generic/socket.h
    creds = sock.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, struct.calcsize('3i'))
    pid, uid, gid = struct.unpack('3i', creds)
    return PeerCredentials(uid, gid, pid)



class IcpProtocol(Protocol):
    '''
        @summary: 
    '''
    
    ICP_WAITING_LEN, ICP_WAITING_BODY = range(2)
        
    def __init__(self, factory):
        self.factory = factory
        self.ctorMapper = buildMethodDescriptor(ICP_pb2, ICP_METHODS_TO_BIND)
        self.ctorMapper.update(buildMethodDescriptor(ICPS_pb2, ICPS_METHODS_TO_BIND))
        self.ctorMapper[4294967295] = ("FreeRdsVersionInfo", pbRPC_pb2.VersionInfo)
        self.version = None
        self.peerCredentials = None
     
    def connectionMade(self):
        self.data = ''
        self.state = self.ICP_WAITING_LEN
        self.version = None
        self.bodyLen = 0
        
        self.peerCredentials = getPeerCredential(self.transport.socket)
        
    def connectionLost(self, reason):
        self.factory.freeRdsInstance = None
    
    def dataReceived(self, data):
        self.data += data
        
        while len(self.data):
            if self.state == self.ICP_WAITING_LEN:
                if len(self.data) < 4:
                    return
                
                self.bodyLen = struct.unpack("!i", self.data[0:4])[0]
                self.state = self.ICP_WAITING_BODY
                self.data = self.data[4:]
                #print "message, len=%d" % self.bodyLen
            
            if self.state == self.ICP_WAITING_BODY:
                if len(self.data) < self.bodyLen:
                    return
            
                baseRpc = pbRPC_pb2.RPCBase()
                baseRpc.ParseFromString(self.data)
                if baseRpc.isResponse:
                    self.treat_response(baseRpc)
                else:
                    self.treat_request(baseRpc)
                
                self.data = self.data[self.bodyLen:]
                self.state = self.ICP_WAITING_LEN
    
    def answer404(self, pbRpc):
        ''' answers a "404 not found" like message in the pcbRpc terminology
            @param pbRpc: the incoming request that will be used to forge an answer
            @return: 404 as error code 
        '''
        pbRpc.status = pbRPC_pb2.RPCBase.NOTFOUND
        pbRpc.isResponse = True
        pbRpc.payload = ''
        response = pbRpc.SerializeToString()
        self.transport.write( struct.pack("!i", len(response)) )                  
        self.transport.write( response )            
    
        
    def sendMessages(self, messages, msgInPayload):
        
        def sendPayload(msgType, tag, resp, payload, msgInPayload):
            msg = pbRPC_pb2.RPCBase()
            msg.msgType = msgType
            msg.tag = tag
            msg.status = pbRPC_pb2.RPCBase.SUCCESS
            msg.isResponse = resp
            if msgInPayload:
                msg.payload = payload.SerializeToString()
            else:
                msg.versionInfo.major = payload.major
                msg.versionInfo.minor = payload.minor
            response = msg.SerializeToString()
            self.transport.write( struct.pack("!i", len(response)) + response)
        
        for (msgType, tag, isResp, payload) in messages:
            sendPayload(msgType, tag, isResp, payload, msgInPayload)

        
    def treat_request(self, pbRpc):
        payload = pbRpc.payload            
            
        cbInfos = self.ctorMapper.get(pbRpc.msgType, None)         
        if cbInfos is None:
            logger.error("PbRpcHandler(): unknown method with id=%d" % pbRpc.msgType)
            return self.answer404(pbRpc)
        
        (methodName, ctor) = cbInfos
        toCall = getattr(self.factory, methodName, None)
        if not callable(toCall):
            logger.error("PbRpcHandler(): unknown method with id=%d" % pbRpc.msgType)
            return self.answer404(pbRpc)                        
                     
        if pbRpc.msgType == VERSION_INFO_MSGTYPE:
            obj = pbRpc.versionInfo
        else:
            obj = ctor()
            obj.ParseFromString(payload)

        ret = toCall(pbRpc, obj)
        if not ret:
            return
        if not isinstance(ret, list):
            ret = [(pbRpc.msgType, pbRpc.tag, True, ret)]
            
        return self.sendMessages(ret, pbRpc.msgType != VERSION_INFO_MSGTYPE)

    def treat_response(self, pbRpc):
        ret = self.factory.treat_response(pbRpc)
        if ret:
            self.sendMessages(ret, True)
                
            
          

class IcpFactory(ServerFactory):
    '''
        @summary: 
    '''
    
    def __init__(self, server):
        self.requestsToInitiate = []
        self.requestsInProgress = {}
        self.tagCounter = 1
        self.freeRdsInstance = None
        self.serverCore = server


    def buildProtocol(self, addr):
        logger.info("FreeRDS connected")
        self.freeRdsInstance = IcpProtocol(self)
        return self.freeRdsInstance
    
    def buildQuery(self, msgType, payload, handler):
        self.tagCounter += 1
        self.requestsInProgress[self.tagCounter] = handler
        return (msgType, self.tagCounter, False, payload)

    def buildResponse(self, msgType, tag, payload):
        return (msgType, tag, True, payload)

    
    def doQuery(self, msgType, payload, handler):
        msg = self.buildQuery(msgType, payload, handler)
        return self.freeRdsInstance.sendMessages( [ msg ], True )
        
    def treat_response(self, msg):
        reqContext = self.requestsInProgress.get(msg.tag, None)
        if not reqContext:
            logger.error("treat_response(): receiving a response(tag=%d type=%d) but no request is registered here" % (msg.tag, msg.msgType))
            return None
                
        del self.requestsInProgress[msg.tag]
        return reqContext.handle(msg.status, msg.payload)


    #
    # ICP requests
    #
    def FreeRdsVersionInfo(self, pbrpc, msg):
        logger.info("FreeRDS protocol version %s.%s" % (msg.major, msg.minor))
        ret = pbRPC_pb2.VersionInfo()
        ret.major = 1
        ret.minor = 0
        return ret

    def IsChannelAllowed(self, pbrpc, msg):
        logger.debug("IsChannelAllowed(%s)" % msg.ChannelName)
        ret = ICP_pb2.IsChannelAllowedResponse()
        ret.channelAllowed = True
        return ret
    
    def LogonUser(self, pbrpc, msg):
        logger.debug("LogonUser(connectionId=%s user=%s password=%s domain=%s hostName=%s)" % (msg.connectionId, \
                    msg.username, msg.password, msg.domain, msg.clientHostName))
        ret = ICP_pb2.LogonUserResponse()

        props = {
                 "width": msg.width,
                 "height": msg.height,
                 "colorDepth": msg.colorDepth,
                 "hostname": msg.clientHostName,
                 "address": msg.clientAddress,
                 "buildNumber": msg.clientBuildNumber,
                 "hardwareId": msg.clientHardwareId,
                 "protocolType": msg.clientProtocolType
        }
        session = self.serverCore.logonUser(msg.connectionId, msg.username, msg.password, msg.domain, props)
        pipeName = None
        if not session.isAuthenticated():                        
            pipeName = self.serverCore.retrieveGreeter(session)
        else:
            pipeName = self.serverCore.retrieveDesktop(session)
            
        self.serverCore.sessionNotification.SessionNotification(wtsapi.WTSConnected, session.sessionId)
        ret.serviceEndpoint = "\\\\.\\pipe\\%s" % pipeName
        ret.maxHeight = 2000
        ret.maxWidth = 4000
        return ret

    def DisconnectUserSession(self, pbrpc, msg):
        logger.debug("DisconnectUserSession(%s)" % msg.connectionId)
        
        session = self.serverCore.retrieveSessionByConnectionId(msg.connectionId)
        if session:
            session.close()
            self.serverCore.removeSession(session)
        
        
        ret = ICP_pb2.DisconnectUserSessionResponse()
        ret.disconnected = True
        return ret
    
    def EndSession(self, pbrpc, msg):
        logger.debug("EndSession(%s)" % msg.sessionId)
        ret = ICPS_pb2.EndSessionResponse()

        session = self.serverCore.retrieveSession(msg.sessionId)        
        if session is None or session.connectionId is None:
            ret.success = False
            return ret
        
        ret.success = True  
    
        logoffReq = ICP_pb2.LogoffUserSessionRequest()
        logoffReq.connectionId = session.connectionId
        
        session.state = wtsapi.WTSDisconnected

        return [
            self.buildResponse(pbrpc.msgType, pbrpc.tag, ret),
            self.buildQuery(ICP_pb2.LogoffUserSession, logoffReq, LogoffHandler(self, session))
        ]  
        
    def RemoteControlEnded(self, pbrpc, msg):
        logger.debug("RemoteControlEnded(spy=%d spied=%d)" % (msg.spyId, msg.spiedId))
        ret = ICP_pb2.RemoteControlEndedResponse()
        ret.success = True
        return ret 
    
    def PropertyString(self, pbrpc, msg):
        logger.debug("propertyString(%s, %s)" % (msg.connectionId, msg.path))
        ret = ICP_pb2.PropertyStringResponse()
        ret.success = True
        
        key = msg.path
        if key.startswith("freerds."):
            key = key[len("freerds."):]

        freerdsConfig = self.serverCore.config['freerds']
        if freerdsConfig.has_key(key):
            ret.value = freerdsConfig[key]
        else:
            logger.error("value %s not found in config" % key)
            ret.success = False
            ret.value = ""
            
        return ret
    
    def PropertyNumber(self, pbrpc, msg):
        logger.debug("propertyNumber(%s, %s)" % (msg.connectionId, msg.path))

        ret = ICP_pb2.PropertyNumberResponse()
        ret.success = False

        key = msg.path
        if key.startswith("freerds."):
            key = key[len("freerds."):]

        freerdsConfig = self.serverCore.config['freerds']
        if freerdsConfig.has_key(key):
            v = freerdsConfig[key]
            if isinstance(v, int):
                ret.value = v 
                ret.success = True
        else:
            logger.error("value %s not found in config" % key)
            ret.value = -1
        
        return ret
    
    def PropertyBool(self, pbrpc, msg):
        logger.debug("propertyBool(%s, %s)" % (msg.connectionId, msg.path))
        ret = ICP_pb2.PropertyBoolResponse()
        
        ret.success = False

        key = msg.path
        if key.startswith("freerds."):
            key = key[len("freerds."):]
        
        freerdsConfig = self.serverCore.config['freerds']
        if freerdsConfig.has_key(key):
            v = freerdsConfig[key]
            if isinstance(v, bool):
                ret.value = v 
                ret.success = True
        else:
            logger.error("value %s not found in config" % key)
            ret.value = -1
        
        return ret
    
    # ============================================================================
    #
    #    ICPS API
    #
    
    def VersionInfo(self, pbrpc, msg):
        ret = ICPS_pb2.VersionInfoResponse()
        ret.major = msg.major
        ret.minor = msg.minor
        return ret
        
    def AuthenticateUser(self, pbrpc, msg):        
        user = msg.username
        password = msg.password
        domain = msg.domain
        logger.debug("Authenticate(sessionId=%s user=%s password=%s domain=%s)" % (msg.sessionId, user, password, domain))
        
        ret = ICPS_pb2.AuthenticateUserResponse()

        session = self.serverCore.retrieveSession(msg.sessionId)
        if session is None:
            logger.error("Authenticate(): no such session %s" % msg.sessionId)
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_INTERNAL_ERROR
            return ret         
        
        if not self.serverCore.authenticate(user, password, domain):
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_BAD_CREDENTIAL
            ret.serviceEndpoint = ""            
            return ret
  
        session.login = user
        session.domain = domain
        session.authenticated = True
        session.state = wtsapi.WTSActive
        
        pipeName = self.serverCore.retrieveDesktop(session)
        if pipeName is None:
            ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_INTERNAL_ERROR
            ret.serviceEndpoint = ""
            return ret
            
        ret.authStatus = ICPS_pb2.AuthenticateUserResponse.AUTH_SUCCESSFULL
        ret.serviceEndpoint = "\\\\.\\pipe\\%s" % pipeName
        
        switchReq = ICP_pb2.SwitchToRequest()
        switchReq.connectionId = session.connectionId
        switchReq.serviceEndpoint = ret.serviceEndpoint
        switchReq.maxWidth = 2000
        switchReq.maxHeight = 2000
                
        return [
            #(msgType, tag, isResp, payload)
            self.buildResponse(pbrpc.msgType, pbrpc.tag, ret),
            self.buildQuery(ICP_pb2.SwitchTo, switchReq, SwitchPipeHandler(self, session, pipeName)) 
        ]
