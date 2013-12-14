import os
import sys
import time
import getpass
import pwd
import stat
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
        ret += "%(" + v[startIndex+2:endIndex-startIndex] + ")s"
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
        super(ContentProviderReaper, self).__init__(name="reaper")            
    
    def run(self):
        while self.doRun:
            try:
                (pid, _retCode, _rusage) = os.wait4(0, os.WNOHANG)
            except:
                pid = 0
            
            if pid:
                print "ContentProviderReaper: caught pid %s" % pid
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
    
    def notifyDeath(self, pid):
        if self.pid != pid:
            print "notifyDeath(): strange notified pid is not mine, self.pid=%s pid=%s" % (self.pid, pid)
            return        
        self.alive = False
    
    def buildEnv(self, globalConfig, context):
        runEnv = {}        
        baseEnv = {                  
            'FREERDS_SID': "${sessionId}",            
            'FREERDS_USER': '${user}',
            'FREERDS_DOMAIN': '${domain}'
        }
        baseEnv.update(self.env)

        for k, v in baseEnv.items():
            if v.find("${") >= 0:
                v = convertFormatString(v) % context
            runEnv[k] = v
            
        if globalConfig.global_ld_library_path:
            runEnv['LD_LIBRARY_PATH'] = ":".join(globalConfig.global_ld_library_path)        
        return runEnv
    
    
    def buildArgs(self, globalConfig, context, extraArgs):
        args = []
        for arg in self.baseArgs + extraArgs:
            if arg.find("${") >= 0:
                arg = convertFormatString(arg) % context
            args.append(arg)
        return args
        
    def build_xdg_runtime_requirements(self, xdg_runtime_dir, owner):
        try:
            xdg_mode = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            if not os.path.exists(xdg_runtime_dir):
                print "build_xdg_runtime_requirements(): directory %s does not exist" % xdg_runtime_dir
                os.mkdir(xdg_runtime_dir, xdg_mode)
                os.system("chown %s %s" % (owner, xdg_runtime_dir))
            else:
                mode = os.stat(xdg_runtime_dir).st_mode 
                if (mode & (stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)) != xdg_mode:
                    print "build_xdg_runtime_requirements(): invalid rights for %s, changing from %o to 0700" % (xdg_runtime_dir, mode)
                    os.chmod(xdg_runtime_dir, (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR))
                
            return True
        except Exception, e:
            print "build_xdg_runtime_requirements(): error during xdg runtime, e=%s" % e
            return False

     
    def impersonnateTo(self, globalConfig, runAs, context, env):
        if runAs is None:
            return True
        if runAs.find("${") >= 0:
            runAs = convertFormatString(runAs) % context
        username = getpass.getuser()
        if username == runAs:
            return True
                
        try:
            targetUser = pwd.getpwnam(runAs)
        except Exception, e:
            print "impersonnateTo(): unable to retrieve user %s, e=%s" % (runAs, e)
            return False
        
        # create the environment
        env["HOME"] = targetUser.pw_dir
        env["XDG_RUNTIME_DIR"] = "/run/user/%s" % runAs
        env['USER'] = runAs
        env['LOGNAME'] = runAs
        env['SHELL'] = targetUser.pw_shell
        env['PATH'] = ":".join(globalConfig.global_user_default_path)
        
        if not self.build_xdg_runtime_requirements(env["XDG_RUNTIME_DIR"], runAs):
            return False

        #print "targetUser %s: uid=%d gid=%s" % (runAs, targetUser.pw_uid, targetUser.pw_gid)       
        try:
            os.setuid(targetUser.pw_uid)
        except Exception, e:
            print "impersonnateTo(): unable to setuid(%s), e=%s" % (targetUser.pw_uid, e)
            return False
                
        return True
    
    def launch(self, globalConfig, reaper, session, extraArgs = [], runAs = None):
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
        
        try:
            self.pid = os.fork()
        except Exception, e:            
            print "launch(): unable to fork(), e=%s" % e
            return False
                        
        if self.pid == 0:                             
            # prepare env variables 
            runEnv = self.buildEnv(globalConfig, context)
            
            if not self.impersonnateTo(globalConfig, runAs, context, runEnv):
                print "launch(): unable to impersonnate to %s" % runAs
                sys.exit(1)

            # prepare command line args
            args = [self.appPath] + self.buildArgs(globalConfig, context, extraArgs)                   
        
            #print "running %s %s env=%s" % (self.appPath, args, runEnv)
            try:
                os.execve(self.appPath, args, runEnv)
            except Exception, e:
                print "launch(): error when executing %s %s" % (e, " ".join(args))
                sys.exit(1)
        
            # /!\ /!\ /!\  /!\ /!\      
            # we should _never_ reach that point
        
        self.alive = True
        reaper.registerProvider(self, self.pid)

        timeout = globalConfig.global_pipeTimeout
        while timeout > 0:
            if os.path.exists(self.pipePath):
                break
            time.sleep(0.1)
            timeout -= 0.1
        
        if not os.path.exists(self.pipePath):
            print "launch(): application %s was not fast enought to start to %s" % (self.appPath, self.pipePath)
            return None
        return self.pipeName
    
    def prepareConnection(self, globalConfig):
        ''' by default there's nothing to do, as the application itself is the 
            content provider '''
        return True
        
        
class StaticContentProvider(SessionManagerContentProvider):
    '''
        @summary: the most trivial content provider, it wires on an existing pipe
                from a pre-launched application. Very useful for debugging purpose
    '''
    __name__ = 'static'

    def launch(self, globalConfig, reaper, session, extraArgs, runAs):
        self.pipeName = self.appPath
        self.pipePath = os.path.join(globalConfig.global_pipesDirectory, self.appPath)
        self.pid = -1
        self.alive = True
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
    
        
    def buildArgs(self, globalConfig, context, extraArgs):
        (width, height) = globalConfig.weston_initialGeometry.split("x")
        ret = ['--backend=freerds-backend.so', 
               '--width=%s' % width,
               '--height=%s' % height, 
               '--freerds-pipe=%s' % context['pipePath']
        ] 
        return ret + super(WestonContentProvider, self).buildArgs(globalConfig, context, extraArgs)


class X11ContentProvider(SessionManagerContentProvider):
    __name__ = 'X11'

    def __init__(self, appName, appPath, baseArgs):
        SessionManagerContentProvider.__init__(self, appName, appPath, baseArgs)
        self.wmPid = None
        self.display = None
       
         
    def buildArgs(self, globalConfig, context, extraArgs):
        (width, height) = globalConfig.x11_initialGeometry.split("x")
        ret = [':1',
               '-depth', globalConfig.x11_depth,
               '-uds',
               '-geometry %sx%s' % (width, height),
               '-terminate'               
        ] 
        return ret + super(X11ContentProvider, self).buildArgs(globalConfig, context, extraArgs)

    def prepareConnection(self, globalConfig, context):
        self.wmPid = os.fork()
        if self.wmPid < 0:
            print "X11ContentProvider: unable to fork for to launch the wm"
            return False
        
        if self.wmPid != 0:
            return True

        '''
        env = self.buildEnv(globalConfig, context)                
        os.execl()
        '''
        return True
    