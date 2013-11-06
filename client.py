import pbRPC_pb2
import ICP_pb2

import socket
import struct

name_to_id = {
    "PingRequest": ICP_pb2.Ping
}

class IcpStub(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/tmp/.pipe/FreeRDS_SessionManager")
        
    def __getattr__(self, name):
        msgType = name_to_id[name]
        def wrapper(msg):
            return self.send(msgType, msg)
        return wrapper
        
    def send(self, type, msg):
        rawMsg = msg.SerializeToString()
        
        headers = pbRPC_pb2.RPCBase()
        headers.tag = 0
        headers.msgType = type
        headers.isResponse = False
        headers.status = pbRPC_pb2.RPCBase.SUCCESS
        rawHeaders = headers.SerializeToString()

        lenBytes = struct.pack("!I", len(rawMsg) + len(rawHeaders)) 
        self.sock.send( lenBytes )
        self.sock.send( rawHeaders )
        self.sock.send( rawMsg )




if __name__ == '__main__':
    stub = IcpStub()
    
    msg = ICP_pb2.PingRequest()
    
    '''
    msg = pbRPC_pb2.RPCBase()
    msg.tag = 0
    msg.msgType = ICP_pb2.ICP.PingRequest
    msg.isResponse = False
    msg.status = pbRPC_pb2.RPCBase.SUCCESS
    '''
    stub.PingRequest(msg)
    
    