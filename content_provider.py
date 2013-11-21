import os
import sys
import time

def convertFormatString(v):
    ret = ""
    startPos = 0
    while True:
        #               v startIndex
        #    ...........${var}
        # startPos^          ^ endIndex
        startIndex = v.find("${", startPos)
        if startIndex < 0:
            ret += v[startPos:]
            return ret
        
        endIndex = v.find("}", startIndex+2)
        if endIndex < 0: 
            ret += v[startPos:]
            return ret
        
        ret += v[startPos : startIndex-startPos]
        ret += "%(" + v[startIndex+2:endIndex-startIndex-2] + ")s"
        startPos = endIndex + 1


class SessionManagerContentProvider(object):
    '''
        @summary:  
    '''
    
    def __init__(self, appName, appPath, baseArgs):
        self.appName = appName
        self.appPath = appPath
        self.env = {}
        self.baseArgs = []
        self.pid = None
        
    def buildEnv(self, globalConfig, context):
        runEnv = {}
        for k, v in self.env.items():
            if v.contains("${"):
                v = convertFormatString(v) % context
            runEnv[k] = v
            
        if len(globalConfig.global_ld_library_path):
            runEnv['LD_LIBRARY_PATH'] = ":".join(globalConfig.global_ld_library_path)
        return runEnv
    
    def buildArgs(self, globalConfig, context, extraArgs):
        args = []
        for arg in self.baseArgs + extraArgs:
            if arg.contains("${"):
                arg = convertFormatString(arg) % arg
            args.append(arg)
        return args
        
        
    def launch(self, globalConfig, sessionId, extraArgs = []):
        pipeName = "FreeRds_%s_%s" % (sessionId, self.appName)
        pipePath = os.path.join(globalConfig.global_pipesDirectory, pipeName)
        context = {
            "pipeName": pipeName,
            "pipePath": pipePath,
            "sessionId": "%s" % sessionId
        }
        
        if os.path.exists(pipePath):
            os.remove(pipePath)
            
        pid = os.fork()
        if pid < 0:            
            print "launch(): unable to fork()"
            return False
                
        if pid == 0:
            runEnv = self.buildEnv(globalConfig, context)
            args = [self.appPath] + self.buildArgs(globalConfig, context, extraArgs)                   
        
            retCode = os.execvpe(self.appPath, args, runEnv)
            if retCode < 0:
                print "error when executing %s %s" % " ".join(args)
                sys.exit(1)
            print "unreachable"
            # we should _never_ reach that point
        
        timeout = globalConfig.global_pipeTimeout
        while timeout > 0:
            if os.path.exists(pipePath):
                break
            time.sleep(0.1)
            timeout -= 0.1
        
        if not os.path.exists(pipePath):
            print "application %s was not fast enought to start to %s" % (self.appPath, pipePath)
            return None
        return (pid, pipeName)
        

class QtContentProvider(SessionManagerContentProvider):
    __name__ = 'qt'
    
    def buildEnv(self, globalConfig, context):
        ret = super(QtContentProvider, self).buildEnv(globalConfig, context)
        if globalConfig.qt_pluginsPath:
            ret['QT_PLUGIN_PATH'] = globalConfig.qt_pluginsPath 
        ret[globalConfig.qt_variableName] = context["pipePath"]
        return ret
    
    def buildArgs(self, globalConfig, context, extraArgs):
        (width, height) = globalConfig.qt_initialGeometry.split("x")
        ret = ['-platform', 'freerds:width=%s:height=%s' % (width, height)] 
        return ret + super(QtContentProvider, self).buildArgs(globalConfig, context, extraArgs)


class WestonContentProvider(SessionManagerContentProvider):
    __name__ = 'weston'
        
    def buildEnv(self, globalConfig, context):
        ret = super(WestonContentProvider, self).buildEnv(globalConfig, context)
        ret['XDG_RUNTIME_DIR'] = os.getenv('XDG_RUNTIME_DIR')
        return ret
        
    def buildArgs(self, globalConfig, context, extraArgs):
        (width, height) = globalConfig.weston_initialGeometry.split("x")
        ret = ['--backend=freerds-backend.so', 
               '--width=%s' % width,
               '--height=%s' % height, 
               '--freerds-pipe=%s' % context['pipePath']
        ] 
        return ret + super(WestonContentProvider, self).buildArgs(globalConfig, context, extraArgs)
