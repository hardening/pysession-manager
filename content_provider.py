import os
import sys
import time
from threading import Thread, RLock

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


class ContentProviderReaper(Thread):
    '''
        @summary: a thread that will wait4() child process and notify 
                content_providers that the underlying process has died
    '''
    def __init__(self):
        self.doRun = True
        self.providers = {}
        self.providersLock = RLock()    
        Thread.__init__(self, name="ContentProviderReaper")        
            
    def run(self):
        while self.doRun:
            pid = 0
            try:
                (pid, _exitStatus) = os.wait4(-1, os.WNOHANG)
            except:
                pid = 0
                        
            if pid != 0:                
                with self.providersLock:
                    provider = self.providers.get(pid, None)
                    if provider:
                        provider.notifyDeath()
                        del self.providers[pid]
                        
            time.sleep(0.1)
            
    def registerProvider(self, p):
        with self.providersLock:
            self.providers[p.pid] = p
            

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
        self.pipeName = None
        self.pipePath = None
        self.alive = False
        
    def isAlive(self):
        return self.alive
    
    def notifyDeath(self):
        self.alive = False
    
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
        
        
    def launch(self, globalConfig, reaper, session, extraArgs = []):
        self.pipeName = "FreeRds_%s_%s" % (session.getId(), self.appName)
        self.pipePath = os.path.join(globalConfig.global_pipesDirectory, self.pipeName)
        context = {
            "pipeName": self.pipeName,
            "pipePath": self.pipePath,
            "sessionId": "%s" % session.getId(),
            "user": session.login,
            "domain": session.domain
        }
        
        if os.path.exists(self.pipePath):
            os.remove(self.pipePath)
            
        self.pid = os.fork()
        if self.pid < 0:            
            print "launch(): unable to fork()"
            return False
                
        self.alive = True
        reaper.registerProvider(self)
        
        if self.pid == 0:
            # prepare env variables 
            runEnv = self.buildEnv(globalConfig, context)
            runEnv['FREERDS_SID'] = "%s" % session.getId()
            runEnv['FREERDS_USER'] = session.login
            runEnv['FREERDS_DOMAIN'] = session.domain
            
            # prepare command line args
            args = [self.appPath] + self.buildArgs(globalConfig, context, extraArgs)                   
        
            retCode = os.execvpe(self.appPath, args, runEnv)
            if retCode < 0:
                print "error when executing %s %s" % " ".join(args)
                sys.exit(1)
            print "unreachable"
            # we should _never_ reach that point
        
        timeout = globalConfig.global_pipeTimeout
        while timeout > 0:
            if os.path.exists(self.pipePath):
                break
            time.sleep(0.1)
            timeout -= 0.1
        
        if not os.path.exists(self.pipePath):
            print "application %s was not fast enought to start to %s" % (self.appPath, self.pipePath)
            return None
        return self.pipeName
        

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
