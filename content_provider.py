import os
import sys
import time
import pwd
import stat
import logging
from twisted.internet import protocol, reactor


logger = logging.getLogger("contentProvider")

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
        
        ret += v[startPos : startIndex]
        ret += "%(" + v[startIndex+2 : endIndex] + ")s"
        startPos = endIndex + 1

def expandVars(strIn, context):
    if strIn.find("${") < 0:
        return strIn
    
    fmt = convertFormatString(strIn)
    return fmt % context
    

PROCESS_INIT, PROCESS_RUNNING, PROCESS_FINISHED = range(0, 3)

class ContentProviderProcess(protocol.ProcessProtocol):
    ''' '''

    def __init__(self):
        self.state = PROCESS_INIT
        self.pid = None
    
    def connectionMade(self):
        ''' process started '''
        logger.debug("process %d running" % self.transport.pid)
        self.state = PROCESS_RUNNING
        self.pid = self.transport.pid

    def outReceived(self, data):
        ''' 'process stdout '''
        #print "%s" % data
        pass
    
    def errReceived(self, data):
        ''' 'process stderr '''
        #print "%s" % data
        pass

    def processExited(self, reason):
        logger.debug("process exited")
        
    def processEnded(self, reason):
        logger.debug("process stopped")
        self.state = PROCESS_FINISHED

    def isAlive(self):
        return self.state == PROCESS_RUNNING
    


class ContentProvider(object):
    '''
        @summary:  
    '''
    
    def __init__(self, appName, appPath, baseArgs):
        self.appName = appName
        self.appPath = appPath
        self.env = {}
        self.baseArgs = []
        self.pipeName = None
        self.pipePath = None
        self.targetUser = None
        self.contextVars = {}
        self.mainProcess = None

        
    def buildEnv(self, globalConfig, context):
        runEnv = {}        
        baseEnv = {                  
            'FREERDS_SID': "${sessionId}",            
            'FREERDS_USER': '${user}',
            'FREERDS_DOMAIN': '${domain}',
            'FREERDS_UID': '${freerds_uid}',
            'FREERDS_PID': '${freerds_pid}',
        }
        baseEnv.update(self.env)

        for k, v in baseEnv.items():
            runEnv[k] = expandVars(v, context)
            
        globalConf = globalConfig['globalConfig'] 
        if globalConf.get('ld_library_path', None):
            runEnv['LD_LIBRARY_PATH'] = ":".join(globalConf['ld_library_path'])        
        return runEnv
    
    
    def buildArgs(self, globalConfig, context, extraArgs):
        args = []
        for arg in self.baseArgs + extraArgs:
            args.append( expandVars(arg, context) )
        return args
        
    def build_xdg_runtime_requirements(self, xdg_runtime_dir, owner):
        try:
            xdg_mode = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            if not os.path.exists(xdg_runtime_dir):
                logger.info("build_xdg_runtime_requirements(): runtime directory %s does not exist" % xdg_runtime_dir)
                os.mkdir(xdg_runtime_dir, xdg_mode)
                os.system("chown %s %s" % (owner, xdg_runtime_dir))
            else:
                mode = os.stat(xdg_runtime_dir).st_mode 
                if (mode & (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)) != xdg_mode:
                    logger.info("build_xdg_runtime_requirements(): invalid rights for %s, changing from %o to 0700" % (xdg_runtime_dir, mode))
                    os.chmod(xdg_runtime_dir, (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR))
                
            return True
        except Exception, e:
            logger.error("build_xdg_runtime_requirements(): error during xdg runtime, e=%s" % e)
            return False

     
    def impersonnateTo(self, globalConfig, pwdInfos, context, env):
        # create the environment
        globalConf = globalConfig['globalConfig']
        env["HOME"] = pwdInfos.pw_dir
        env["XDG_RUNTIME_DIR"] = expandVars(globalConf['xdg_runtime_schema'], context)
        env['LOGNAME'] = env['USER'] = pwdInfos.pw_name
        env['SHELL'] = pwdInfos.pw_shell
        env['PATH'] = ":".join(globalConf['user_default_path'])
        
        # this should be a no-op if no impersonification is needed
        return self.build_xdg_runtime_requirements(env["XDG_RUNTIME_DIR"], pwdInfos.pw_name)
    
    def launch(self, sm, session, extraArgs, runAs = None, peerCredentials = None):
        globalConfig = sm.config
        globalConf = globalConfig['globalConfig']

        self.pipeName = "FreeRDS_%s_%s" % (session.getId(), self.appName)
        self.pipePath = os.path.join(globalConf['pipesDirectory'], self.pipeName)
        
        if os.path.exists(self.pipePath):
            os.remove(self.pipePath)

        self.contextVars = {
            "pipeName": self.pipeName,
            "pipePath": self.pipePath,
            "sessionId": "%s" % session.getId(),
            "user": session.login,
            "domain": session.domain,
        }
        
        if peerCredentials:
            self.contextVars["freerds_pid"] = peerCredentials.pid
            self.contextVars["freerds_uid"] = peerCredentials.uid

        currentUid = os.getuid()

        runAsUid = None
        runAsGid = None
        if runAs is None:
            try:
                runAsUid = currentUid
                pwdInfos = pwd.getpwuid(runAsUid)
                runAs = pwdInfos.pw_name
            except Exception, e:
                logger.error("launch(): unable to retrieve my login name, e=%s" % e)
                return False
        else:
            try:
                pwdInfos = pwd.getpwuid(runAs)
                runAsUid = pwdInfos.pw_uid
            except Exception, e:
                logger.error("launch(): unable to retrieve target runAs account %s, e=%s" % (runAs, e))
                return False

        runAsGid = pwdInfos.pw_gid

        self.targetUser = expandVars(runAs, self.contextVars)
        self.contextVars["runAsUser"] = self.targetUser
        self.contextVars["runAsUserId"] = "%s" % runAsUid
        self.contextVars["runAsGroupId"] = "%s" % runAsGid

        runEnv = self.buildEnv(globalConfig, self.contextVars)
        
        # prepare command line args
        args = [os.path.basename(self.appPath)]
        args += self.buildArgs(globalConfig, self.contextVars, extraArgs)

        if not self.impersonnateTo(globalConfig, pwdInfos, self.contextVars, runEnv):
            logger.error("launch(): unable to impersonnate to %s" % self.targetUser)
            return False

        targetUid = runAsUid
        targetGid = runAsGid
        if runAsUid == currentUid:
            targetUid = None
            targetGid = None
            
        self.mainProcess = reactor.spawnProcess(self, self.appPath, args, runEnv, pwdInfos.pw_dir,
                            targetUid, targetGid, False)
        
        timeout = globalConf['pipeTimeout']
        while timeout > 0:
            if os.path.exists(self.pipePath):
                break
            time.sleep(0.1)
            timeout -= 0.1
        
        if not os.path.exists(self.pipePath):
            logger.error("launch(): application %s was not fast enough to start to %s" % (self.appPath, self.pipePath))
            return None
        return self.pipeName
    
    def initProvider(self, globalConfig):
        ''' by default there's nothing to do, as the application itself is the 
            content provider '''
        return True
    
    def close(self):
        if not self.isAlive():
            logger.debug("backend already dead")
            return

        try:
            self.mainProcess.signalProcess("TERM")
        except Exception, e:
            logger.error("caught an exception when sending SIGTERM to the content provider, e=%s" % e)
            return

        def warnNotKilled(provider):
            # used to print an error message if we didn't manage to receive the death signal in time
            if provider.isAlive():
                logger.warn("failed to reap contentProvider with pid %s" % provider.mainProcess.pid) 

        def sigKillIfNeeded(provider):
            # callback that will send a SIGKILL if SIGTERM was not sufficient
            if not provider.isAlive():
                logger.debug("provider killed in time")
                return

            try:
                provider.mainProcess.signalProcess("KILL")
            except Exception, e:
                logger.error("caught an exception when sending SIGKILL to the content provider, e=%s" % e)
                return
            reactor.callLater(1.0, warnNotKilled, provider)

        reactor.callLater(1.0, sigKillIfNeeded, self)

        
        
        
class StaticContentProvider(ContentProvider):
    '''
        @summary: the most trivial content provider, it wires on an existing pipe
                from a pre-launched application. Very useful for debugging purpose
    '''
    __name__ = 'static'

    def launch(self, sm, session, extraArgs, runAs, peerCredentials):
        globalConfig = sm.config

        self.pipeName = self.appPath
        self.pipePath = os.path.join(globalConfig['globalConfig']['pipesDirectory'], self.appPath)
        self.pid = -1
        self.alive = True
        return self.pipeName

    def close(self):
        ''' it's a no-op for the static content provider '''
        pass

    def isAlive(self):
        return os.path.exists(self.pipePath)



class QtContentProvider(ContentProvider, ContentProviderProcess):
    '''
        @summary: 
    '''
    __name__ = 'qt'
    
    def buildEnv(self, globalConfig, context):
        qtConfig = globalConfig['qt']
        ret = super(QtContentProvider, self).buildEnv(globalConfig, context)
        if qtConfig['pluginsPath']:
            ret['QT_PLUGIN_PATH'] = qtConfig['pluginsPath'] 
        ret[qtConfig['variableName']] = context["pipePath"]
        return ret
    
    def buildArgs(self, globalConfig, context, extraArgs):
        qtConfig = globalConfig['qt']
        (width, height) = qtConfig['initialGeometry'].split("x")
        ret = ['-platform', 'freerds:width=%s:height=%s' % (width, height)] 
        return ret + super(QtContentProvider, self).buildArgs(globalConfig, context, extraArgs)


class WestonContentProvider(ContentProvider, ContentProviderProcess):
    '''
        @summary: 
    '''
    __name__ = 'weston'
    
        
    def buildArgs(self, globalConfig, context, extraArgs):
        westonConfig = globalConfig['weston']
        (width, height) = westonConfig['initialGeometry'].split("x")
        self.appPath = westonConfig['serverPath']
        ret = ['--backend=freerds-backend.so', 
               '--width=%s' % width,
               '--height=%s' % height, 
               '--freerds-pipe=%s' % context['pipePath']
        ] 
        return ret + super(WestonContentProvider, self).buildArgs(globalConfig, context, extraArgs)


class X11ContentProvider(ContentProvider, ContentProviderProcess):
    '''
        @summary: 
    '''
    __name__ = 'X11'

    def __init__(self, appName, appPath, baseArgs):
        ContentProvider.__init__(self, 'X11', appPath, baseArgs)
        self.wmPid = None
        self.display = None        
       
         
    def buildArgs(self, globalConfig, context, extraArgs):
        x11config = globalConfig['x11']
        (width, height) = x11config['initialGeometry'].split("x")
        self.appPath = x11config['serverPath']
        ret = [expandVars(':${sessionId}', context),
               '-depth', x11config['depth'],
               '-uds',
               '-geometry %sx%s' % (width, height),
               '-terminate'               
        ] 
        return ret + super(X11ContentProvider, self).buildArgs(globalConfig, context, extraArgs)


    def notifyDeath(self, pid):
        if pid == self.wmPid:
            print "WM has died"
            self.wmPid = -1
            return
            
        if self.pid != pid:
            logger.warn("notifyDeath(): strange notified pid is not mine, self.pid=%s pid=%s" % (self.pid, pid))
            return
        self.alive = False


    def initProvider(self, globalConfig):
        logger.debug("launching WM")
        x11config = globalConfig['x11']
        try:
            self.wmPid = os.fork()
        except Exception, e:
            logger.error("X11ContentProvider: unable to fork to launch the WM, e=%s" % e)
            return False
        
        if self.wmPid == 0:
            # prepare env variables 
            runEnv = self.buildEnv(globalConfig, self.contextVars)
            runEnv['DISPLAY'] = expandVars(":${sessionId}", self.contextVars)
            
            if not self.impersonnateTo(globalConfig, self.targetUser, self.contextVars, runEnv):
                logger.error("launch(): unable to impersonnate to %s" % self.targetUser)
                sys.exit(1)

            # prepare command line args
            args = [x11config['wmPath']] + self.buildArgs(globalConfig, self.contextVars, [])                   
        
            #print "running %s %s env=%s" % (self.appPath, args, runEnv)
            try:
                os.execve(x11config['wmPath'], args, runEnv)
            except Exception, e:
                logger.error("launch(): error when executing %s %s" % (e, " ".join(args)))
                sys.exit(1)
        
            # /!\ /!\ /!\  /!\ /!\      
            # we should _never_ reach that point

        self.reaper.registerProvider(self, self.wmPid)
        return True
    