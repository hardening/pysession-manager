import os
import sys
import time
import pwd
import stat
import logging
from threading import Thread, RLock
from signal import SIGTERM

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
    

class ContentProviderReaper(Thread):
    '''
        @summary: a thread that will wait4() child process and notify 
                content_providers that the underlying process has died
    '''
    def __init__(self):
        self.doRun = True
        self.providers = {}
        self.providersLock = RLock()
        super(ContentProviderReaper, self).__init__(name="reaper")            
    
    def run(self):
        while self.doRun:
            try:
                (pid, _retCode, _rusage) = os.wait4(0, os.WNOHANG)
            except:
                pid = 0
            
            if pid:
                logger.info("ContentProviderReaper: caught pid %s" % pid)
                self.notifyDeath(pid)
            
            time.sleep(0.5)
            
    
    def notifyDeath(self, pid):
        with self.providersLock:
            provider = self.providers.get(pid, None)            
            if provider:
                provider.notifyDeath(pid)
                del self.providers[pid]
        
            
    def registerProvider(self, p, pid):
        with self.providersLock:
            self.providers[pid] = p
    
    def doStop(self):
        self.doRun = False
            

class ContentProvider(object):
    '''
        @summary:  
    '''
    
    def __init__(self, appName, appPath, baseArgs):
        self.appName = appName
        self.appPath = appPath
        self.env = {}
        self.baseArgs = []
        self.pid = -1
        self.pipeName = None
        self.pipePath = None
        self.alive = False
        self.targetUser = None
        self.contextVars = {}
        self.reaper = None
        
    def isAlive(self):
        return self.alive
    
    def notifyDeath(self, pid):
        if self.pid != pid:
            logger.warn("notifyDeath(): strange notified pid is not mine, self.pid=%s pid=%s" % (self.pid, pid))
            return        
        self.alive = False
        self.pid = -1
    
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
        if globalConf['ld_library_path']:
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
                logger.info("build_xdg_runtime_requirements(): directory %s does not exist" % xdg_runtime_dir)
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

     
    def impersonnateTo(self, globalConfig, targetUser, context, env):
        currentUser = pwd.getpwuid( os.getuid() ).pw_name
        
        try:
            userInfos = pwd.getpwnam(targetUser)
        except Exception, e:
            logger.error("impersonnateTo(): unable to retrieve user %s, e=%s" % (targetUser, e))
            return False
                
        # create the environment
        globalConf = globalConfig['globalConfig']
        env["HOME"] = userInfos.pw_dir
        env["XDG_RUNTIME_DIR"] = expandVars(globalConf['xdg_runtime_schema'], context)
        env['USER'] = targetUser
        env['LOGNAME'] = targetUser
        env['SHELL'] = userInfos.pw_shell
        env['PATH'] = ":".join(globalConf['user_default_path'])
        
        # this should be a no-op if no impersonification is needed
        if not self.build_xdg_runtime_requirements(env["XDG_RUNTIME_DIR"], targetUser):            
            return False

        if currentUser == targetUser:
            return True

        #print "targetUser %s: uid=%d gid=%s" % (runAs, targetUser.pw_uid, targetUser.pw_gid)       
        try:
            os.setuid(userInfos.pw_uid)
        except Exception, e:
            logger.error("impersonnateTo(): unable to setuid(%s), e=%s" % (userInfos.pw_uid, e))
            return False
                
        return True
    
    def launch(self, globalConfig, reaper, session, extraArgs, runAs = None, peerCredentials = None):
        globalConf = globalConfig['globalConfig']
        if runAs is None:
            runAs = pwd.getpwuid( os.getuid() ).pw_name

        self.pipeName = "FreeRDS_%s_%s" % (session.getId(), self.appName)
        self.pipePath = os.path.join(globalConf['pipesDirectory'], self.pipeName)
        
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

        self.targetUser = expandVars(runAs, self.contextVars)
        self.contextVars["runAsUser"] = self.targetUser
        self.contextVars["runAsUserId"] = pwd.getpwnam(self.targetUser).pw_uid

        self.reaper = reaper
        
        if os.path.exists(self.pipePath):
            os.remove(self.pipePath)
        
        try:
            self.pid = os.fork()
        except Exception, e:            
            logger.error("launch(): unable to fork(), e=%s" % e)
            return False
                        
        self.alive = True
        reaper.registerProvider(self, self.pid)

        if self.pid == 0:                             
            # prepare env variables 
            runEnv = self.buildEnv(globalConfig, self.contextVars)
            
            if not self.impersonnateTo(globalConfig, self.targetUser, self.contextVars, runEnv):
                logger.error("launch(): unable to impersonnate to %s" % self.targetUser)
                sys.exit(1)

            # prepare command line args
            args = [self.appPath] + self.buildArgs(globalConfig, self.contextVars, extraArgs)                   
        
            #print "running %s %s env=%s" % (self.appPath, args, runEnv)
            try:
                os.execve(self.appPath, args, runEnv)
            except Exception, e:
                logger.error("launch(): error when executing %s %s" % (e, " ".join(args)))
                sys.exit(1)
        
            # /!\ /!\ /!\  /!\ /!\      
            # we should _never_ reach that point
        
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
        if not self.alive:
            logger.debug("backend still dead")
            return
        
        if self.pid > 0:
            os.kill(self.pid, SIGTERM)
        
        while self.alive:
            time.sleep(0.1)
        
        
class StaticContentProvider(ContentProvider):
    '''
        @summary: the most trivial content provider, it wires on an existing pipe
                from a pre-launched application. Very useful for debugging purpose
    '''
    __name__ = 'static'

    def launch(self, globalConfig, reaper, session, extraArgs, runAs, peerCredentials):
        self.pipeName = self.appPath
        self.pipePath = os.path.join(globalConfig['globalConfig']['pipesDirectory'], self.appPath)
        self.pid = -1
        self.alive = True
        return self.pipeName

    def close(self):
        ''' it's a no-op for the static content provider '''
        pass


class QtContentProvider(ContentProvider):
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


class WestonContentProvider(ContentProvider):
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


class X11ContentProvider(ContentProvider):
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
    