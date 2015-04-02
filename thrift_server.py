from zope.interface import implements

from thrift.transport import TTwisted
from thrift.protocol import TBinaryProtocol

from thrift.server import TServer

import wtsapi
import logging
from fdsapi import fdsapi, ttypes
from pbRPC_pb2 import RPCBase
from ICP_pb2 import FdsApiVirtualChannelOpen, FdsApiVirtualChannelOpenRequest, FdsApiVirtualChannelOpenResponse,\
    FdsApiStartRemoteControl, FdsApiStartRemoteControlRequest, FdsApiStartRemoteControlResponse, \
    FdsApiStopRemoteControl, FdsApiStopRemoteControlRequest, FdsApiStopRemoteControlResponse,\
    FdsApiVirtualChannelCloseRequest, FdsApiVirtualChannelClose,\
    FdsApiVirtualChannelCloseResponse
from icp_server import PbRpcResponseHandler
from twisted.internet.defer import Deferred


logger = logging.getLogger("fdsapi")


class Thrift2IcpHandler(PbRpcResponseHandler):
    ''' '''
    
    def __init__(self, fdsApi, deferred, icpResponseClass):
        super(Thrift2IcpHandler, self).__init__(fdsApi, icpResponseClass)
        self.deferred = deferred
        
    def onResponse(self, status, response):
        if status == RPCBase.SUCCESS:
            self.deferred.callback(response)
        else:
            self.deferred.error("request not successful")
  



class StartRemoteControlHandler(PbRpcResponseHandler):
    '''
        @summary: a pbrpc response handler to request to start shadowing
    '''

    def __init__(self, fdsApi, deferred):
        super(StartRemoteControlHandler, self).__init__(fdsApi, FdsApiStartRemoteControlResponse)
        self.deferred = deferred
        
    def onResponse(self, status, response):
        if status == RPCBase.SUCCESS:
            self.deferred.callback(response)
        else:
            self.deferred.errback("request not successful")


class StopRemoteControlHandler(PbRpcResponseHandler):
    '''
        @summary: a pbrpc response handler to request to stop shadowing
    '''

    def __init__(self, fdsApi, deferred):
        super(StopRemoteControlHandler, self).__init__(self, fdsApi, FdsApiStopRemoteControlResponse)
        self.deferred = deferred
        
    def onResponse(self, status, response):
        if status == RPCBase.SUCCESS:
            self.deferred.callback(response)
        else:
            self.deferred.errback("request not successful")


class FdsApiHandler(object):
    '''
        @summary: the thrift server implementing the FDS API
    '''
    implements(fdsapi.Iface)  
   
    
    def __init__(self, server):
        self.server = server
    
    def getVersionInfo(self, versionInfo):
        return versionInfo

    def logonConnection(self, username, password, domain):
        if not self.server.authenticate(username, password, domain):
            return ttypes.TReturnLogonConnection(False, "")
        
        session = self.server.authenticate(0, username, password, domain, "@ip")
        # TODO: set proper rights and owner
        open("/tmp/freerds.session.%s" % session.getId()).write(session.token)
        return ttypes.TReturnLogonConnection(True, session.token)
    
    def getPermissionForToken(self, authToken):
        return 0xffff
    
    
    def virtualChannelOpen(self, authToken, sessionId, virtualName, isDynChannel, flags):
        """
        Parameters:
         - authToken
         - sessionId
         - virtualName
         - isDynChannel
         - flags
        """
        logger.debug("virtualChannelOpen(auth=%s, sessionId=%s virtualName=%s)" % (authToken, sessionId, virtualName))
        session = self.server.retrieveSession(sessionId)
        if not session:
            logger.error("session %s not present here" % sessionId)
            return ttypes.TReturnVirtualChannelOpen("", 0)
        
        if session.token != authToken:
            logger.error("authToken doesn't match for session %s" % sessionId)
            return ttypes.TReturnVirtualChannelOpen("", 0)
        
        icpFactory = self.server.icpFactory
        req = FdsApiVirtualChannelOpenRequest()
        req.connectionId = session.connectionId
        req.virtualName = virtualName
        req.dynamicChannel = isDynChannel
        req.flags = flags
        
        d = Deferred()
        def onError(err):
            logger.error('an error occured')
            return ttypes.TException('Internal error in server')
        def onSuccess(response):
            logger.debug('returning %s / %s'  % (response.connectionString, response.instance))
            return ttypes.TReturnVirtualChannelOpen(response.connectionString, response.instance)
        
        d.addErrback(onError)
        d.addCallback(onSuccess)
        
        icpFactory.doQuery(FdsApiVirtualChannelOpen, req, Thrift2IcpHandler(self, d, FdsApiVirtualChannelOpenResponse))
        return d
    
    def logonAdminConnection(self, username, password, domain):
        """
        Parameters:
         - username
         - password
         - domain
        """
        pass
    
    def logoffAdminConnection(self, authToken):
        """
        Parameters:
         - authToken
        """
        pass
    
    def ping(self, inp):
        """
        Parameters:
        - input
        """
        return inp
    
    
    def virtualChannelClose(self, authToken, sessionId, virtualName, instance):
        """
        Parameters:
        - authToken
        - sessionId
        - virtualName
        - instance
        """
        logger.debug("virtualChannelClose(auth=%s, sessionId=%s virtualName=%s)" % (authToken, sessionId, virtualName))
        session = self.server.retrieveSession(sessionId)
        if not session:
            logger.error("session %s not present here" % sessionId)
            return False
        
        if session.token != authToken:
            logger.error("authToken doesn't match for session %s" % sessionId)
            return False
        
        icpFactory = self.server.icpFactory
        req = FdsApiVirtualChannelCloseRequest()
        req.connectionId = session.connectionId
        req.virtualName = virtualName
        req.instance = instance
        
        d = Deferred()
        def onError(err):
            logger.error('an error occured')
            return False
        def onSuccess(response):
            logger.debug('returning %s'  % (response.success))
            return response.success
        
        d.addErrback(onError)
        d.addCallback(onSuccess)
        
        icpFactory.doQuery(FdsApiVirtualChannelClose, req, Thrift2IcpHandler(self, d, FdsApiVirtualChannelCloseResponse))
        return d

        
        return True
    
    def disconnectSession(self, authToken, sessionId, wait):
        """
        Parameters:
        - authToken
        - sessionId
        - wait
        """
        return True
    
    def logoffSession(self, authToken, sessionId, wait):
        """
        Parameters:
        - authToken
        - sessionId
        - wait
        """
        return True
    
    def enumerateSessions(self, authToken, Version):
        """
        Parameters:
         - authToken
         - Version
        """
        ret = ttypes.TReturnEnumerateSession()
        ret.returnValue = True
        ret.sessionInfoList = []
        
        for sid, s in self.server.sessions.items():
            sessionInfo = ttypes.TSessionInfo()
            sessionInfo.winStationName = ""
            sessionInfo.sessionId = sid
            sessionInfo.connectState = 0
            
            ret.sessionInfoList.append(sessionInfo)
        
        return ret

    
    def querySessionInformation(self, authToken, sessionId, infoClass):
        """
        Parameters:
        - authToken
        - sessionId
        - infoClass
        """
        ret = ttypes.TReturnQuerySessionInformation()
        ret.returnValue = False
        ret.infoValue = ttypes.TSessionInfoValue()
        
        session = self.server.retrieveSession(sessionId)
        if not session:
            return ret
        
        if infoClass == wtsapi.WTSSessionId:
            ret.infoValue.int32Value = sessionId
        elif infoClass == wtsapi.WTSUserName:
            ret.infoValue.stringValue = session.login
        elif infoClass == wtsapi.WTSClientName:
            ret.infoValue.stringValue = session.hostname or ''
        elif infoClass == wtsapi.WTSLogonTime:
            ret.infoValue.int64Value = 0
        elif infoClass == wtsapi.WTSWinStationName:
            ret.infoValue.stringValue = session.authenticated and 'desktop' or 'greeter'
        elif infoClass == wtsapi.WTSDomainName:
            ret.infoValue.stringValue = session.domain
        elif infoClass == wtsapi.WTSSessionInfo:
            wtsinfo = ret.infoValue.WTSINFO = ttypes.TWTSINFO()
            
            wtsinfo.UserName = session.login
            wtsinfo.Domain = session.domain
            wtsinfo.WinStationName = session.hostname
            wtsinfo.ConnectTime = session.connectTime
            wtsinfo.State = wtsapi.WTSActive
        else:
            logger.warn("%s not coded yet" % infoClass)
            return ret
        
        ret.returnValue = True
        return ret
    
    def startRemoteControlSession(self, authToken, sourceSessionId, targetSessionId, HotkeyVk, HotkeyModifiers):
        """
        Parameters:
         - authToken
         - sessionId
         - targetSessionId
         - HotkeyVk
         - HotkeyModifiers
        """
        logger.debug("startRemoteControlSession(auth=%s, sessionId=%s targetSessionId=%s)" % (authToken, sourceSessionId, targetSessionId))
        session = self.server.retrieveSession(sourceSessionId)
        if not session:
            logger.error("source session %s not present here" % sourceSessionId)
            return False
        
        targetSession = self.server.retrieveSession(targetSessionId)
        if not targetSession:
            logger.error("target session %s not present here" % targetSessionId)
            return False
        
        if targetSession == session:
            logger.error("can't shadow myself id=" % sourceSessionId)
            return False
        
        icpFactory = self.server.icpFactory
        req = FdsApiStartRemoteControlRequest()
        req.connectionId = session.connectionId
        req.targetConnectionId = targetSession.connectionId
        req.hotKeyVk = HotkeyVk
        req.hotKeyModifiers = HotkeyModifiers
        
        d = Deferred()
        def onError(err):
            logger.error('an error occured')
            return ttypes.TException('Internal error in server')
        def onSuccess(response):
            logger.debug('response=%s'  % response)
            return response.success
        
        d.addErrback(onError)
        d.addCallback(onSuccess)
        
        icpFactory.doQuery(FdsApiStartRemoteControl, req, Thrift2IcpHandler(self, d, FdsApiStartRemoteControlResponse))
        return d
    
    def stopRemoteControlSession(self, authToken, sourceLogonId, targetLogonId):
        logger.debug("stopRemoteControlSession(auth=%s, sessionId=%s targetSessionId=%s)" % (authToken, sourceLogonId, targetLogonId))
        session = self.server.retrieveSession(sourceLogonId)
        if not session:
            logger.error("source session %s not present here" % sourceLogonId)
            return False
        
        targetSession = self.server.retrieveSession(targetLogonId)
        if not targetSession:
            logger.error("target session %s not present here" % targetLogonId)
            return False
        
        icpFactory = self.server.icpFactory
        req = FdsApiStopRemoteControlRequest()
        req.connectionId = session.connectionId
        
        d = Deferred()
        def onError(err):
            logger.error('an error occured')
            return ttypes.TException('Internal error in server')
        def onSuccess(response):
            logger.debug('response=%s' % response)
            return response.success
        
        d.addErrback(onError)
        d.addCallback(onSuccess)
        
        icpFactory.doQuery(FdsApiStopRemoteControl, req, Thrift2IcpHandler(self, d, FdsApiStopRemoteControlResponse))
        return d

    
def FdsFactory(server):
    processor = fdsapi.Processor(FdsApiHandler(server))
    pfactory = TBinaryProtocol.TBinaryProtocolFactory()
    
    return TTwisted.ThriftServerFactory(processor, pfactory)
