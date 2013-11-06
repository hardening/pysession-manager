import pbRPC_pb2
import ICP_pb2
import SocketServer
import os, os.path
import time
import struct
import sys

pipeDir = os.path.join("/tmp", ".pipe")

class ProtobufHandler(SocketServer.BaseRequestHandler):
    '''
    '''
    globalId = 0
        
    def GetUserSession(self, getUserReq):
        print "getUserSession"
        ret = ICP_pb2.GetUserSessionResponse()
        ret.SessionID = self.globalId
        self.globalId += 1
        ret.ServiceEndpoint = "\\\\.\\pipe\\FreeRDS_%d_greeter" % ret.SessionID
        
        pipeName = '%s/FreeRDS_%d_greeter' % (pipeDir, ret.SessionID)
        if os.fork() == 0:
            prog = "/home/david/dev/git/qfreerdp_platform/chart.sh"       
            args = [prog, pipeName, '-platform', 'freerds:width=%d:height=%d' % (1024, 768)]
            os.execl(prog, *args)            
        
        waitTime = 0.0
        while waitTime < 10:
            if not os.path.exists(pipeName):
                time.sleep(0.1)
            waitTime -= 0.1
        
        if not os.path.exists(pipeName):
            return None
        return ret
    
    def IsChannelAllowed(self, msg):
        print "IsChannelAllowed(%s)" % msg.ChannelName
        ret = ICP_pb2.IsChannelAllowedResponse()
        ret.ChannelAllowed = True
        return ret
    
    def treat_request(self, rpcbase):
        callbacks = {
               ICP_pb2.IsChannelAllowed: (self.IsChannelAllowed, ICP_pb2.IsChannelAllowedRequest), 
               ICP_pb2.GetUserSession: (self.GetUserSession, ICP_pb2.GetUserSessionRequest)
        }
        
        (cb, ctor) = callbacks.get(rpcbase.msgType, None)
        obj = ctor()
        obj.ParseFromString(rpcbase.payload)
        return cb(obj)
        
        
    def treat_response(self, rpcBase):
        print "treat_response()"
        pass    
        
    
    def handle(self):
        print "client starting"
        while True:
            lenBytes = self.request.recv(4)
            if not len(lenBytes):
                break            
            msgLen = struct.unpack("!i", lenBytes)[0]
            print "msgLen=%s" % msgLen
            
            msg = self.request.recv(msgLen)
            baseRpc = pbRPC_pb2.RPCBase()
            baseRpc.ParseFromString(msg)
            if baseRpc.isResponse:
                self.treat_response(baseRpc)
            else:
                ret = self.treat_request(baseRpc)
                if ret:
                    baseRpc.status = pbRPC_pb2.RPCBase.SUCCESS
                    baseRpc.isResponse = True
                    baseRpc.payload = ret.SerializeToString()
                    response = baseRpc.SerializeToString()
                    self.request.send( struct.pack("!i", len(response)) )                  
                    self.request.send( response )
                        
        print "client finished"
        
        


if __name__ == "__main__": 
    fullPath = os.path.join(pipeDir, "FreeRDS_SessionManager")
    if not os.path.exists(pipeDir):
        os.mkdir(pipeDir)
    if os.path.exists(fullPath):
        os.remove(fullPath)
    
    server = SocketServer.ThreadingUnixStreamServer(fullPath, ProtobufHandler)
    server.serve_forever()
    
